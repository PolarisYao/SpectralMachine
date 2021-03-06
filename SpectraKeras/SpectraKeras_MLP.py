#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
**********************************************************
* SpectraKeras_MLP Classifier and Regressor
* 20181207a
* Uses: Keras, TensorFlow
* By: Nicola Ferralis <feranick@hotmail.com>
***********************************************************
'''
print(__doc__)

import numpy as np
import pandas as pd
import sys, os.path, getopt, time, configparser, pickle, h5py, csv, glob
from libSpectraKeras import *

#***************************************************
# This is needed for installation through pip
#***************************************************
def SpectraKeras_MLP():
    main()

#************************************
# Parameters
#************************************
class Conf():
    def __init__(self):
        confFileName = "SpectraKeras_MLP.ini"
        self.configFile = os.getcwd()+"/"+confFileName
        self.conf = configparser.ConfigParser()
        self.conf.optionxform = str
        if os.path.isfile(self.configFile) is False:
            print(" Configuration file: \""+confFileName+"\" does not exist: Creating one.\n")
            self.createConfig()
        self.readConfig(self.configFile)
        if self.regressor:
            self.modelName = "keras_model_regressor.hd5"
            self.summaryFileName = "keras_summary_regressor.csv"
        else:
            self.modelName = "keras_model.hd5"
            self.summaryFileName = "keras_summary_classifier.csv"
        
        self.tb_directory = "keras_MLP"
        self.model_directory = "./"
        self.model_name = self.model_directory+self.modelName
        self.model_le = self.model_directory+"keras_le.pkl"
        self.spectral_range = "keras_spectral_range.pkl"
        self.model_png = self.model_directory+"/keras_MLP_model.png"
            
    def SKDef(self):
        self.conf['Parameters'] = {
            'regressor' : False,
            'normalize' : False,
            'l_rate' : 0.001,
            'l_rdecay' : 1e-4,
            'HL' : [20,30,40,50,60,70],
            'drop' : 0,
            'l2' : 1e-4,
            'epochs' : 100,
            'cv_split' : 0.01,
            'fullSizeBatch' : False,
            'batch_size' : 64,
            'numLabels' : 1,
            'plotWeightsFlag' : False,
            'showValidPred' : False,
            }

    def sysDef(self):
        self.conf['System'] = {
            'useTFKeras' : False,
            }

    def readConfig(self,configFile):
        try:
            self.conf.read(configFile)
            self.SKDef = self.conf['Parameters']
            self.sysDef = self.conf['System']
        
            self.regressor = self.conf.getboolean('Parameters','regressor')
            self.normalize = self.conf.getboolean('Parameters','normalize')
            self.l_rate = self.conf.getfloat('Parameters','l_rate')
            self.l_rdecay = self.conf.getfloat('Parameters','l_rdecay')
            self.HL = eval(self.SKDef['HL'])
            self.drop = self.conf.getfloat('Parameters','drop')
            self.l2 = self.conf.getfloat('Parameters','l2')
            self.epochs = self.conf.getint('Parameters','epochs')
            self.cv_split = self.conf.getfloat('Parameters','cv_split')
            self.fullSizeBatch = self.conf.getboolean('Parameters','fullSizeBatch')
            self.batch_size = self.conf.getint('Parameters','batch_size')
            self.numLabels = self.conf.getint('Parameters','numLabels')
            self.plotWeightsFlag = self.conf.getboolean('Parameters','plotWeightsFlag')
            self.showValidPred = self.conf.getboolean('Parameters','showValidPred')
            self.useTFKeras = self.conf.getboolean('System','useTFKeras')
        except:
            print(" Error in reading configuration file. Please check it\n")

    # Create configuration file
    def createConfig(self):
        try:
            self.SKDef()
            self.sysDef()
            with open(self.configFile, 'w') as configfile:
                self.conf.write(configfile)
        except:
            print("Error in creating configuration file")

#************************************
# Main
#************************************
def main():
    start_time = time.clock()
    dP = Conf()
    try:
        opts, args = getopt.getopt(sys.argv[1:],
                                   "tpbh:", ["train", "predict", "batch", "help"])
    except:
        usage()
        sys.exit(2)

    if opts == []:
        usage()
        sys.exit(2)

    for o, a in opts:
        if o in ("-t" , "--train"):
            try:
                if len(sys.argv)<4:
                    train(sys.argv[2], None)
                else:
                    train(sys.argv[2], sys.argv[3])
            except:
                usage()
                sys.exit(2)

        if o in ("-p" , "--predict"):
            try:
                predict(sys.argv[2])
            except:
                usage()
                sys.exit(2)
                
        if o in ("-b" , "--batch"):
            try:
                batchPredict()
            except:
                usage()
                sys.exit(2)

    total_time = time.clock() - start_time
    print(" Total time: {0:.1f}s or {1:.1f}m or {2:.1f}h".format(total_time,
                            total_time/60, total_time/3600),"\n")

#************************************
# Training
#************************************
def train(learnFile, testFile):
    import tensorflow as tf
    dP = Conf()
    
    # Use this to restrict GPU memory allocation in TF
    opts = tf.GPUOptions(per_process_gpu_memory_fraction=1)
    conf = tf.ConfigProto(gpu_options=opts)
    conf.gpu_options.allow_growth = True
    
    if dP.useTFKeras:
        print("Using tf.keras API")
        import tensorflow.keras as keras  #tf.keras
        tf.Session(config=conf)
    else:
        print("Using pure keras API")
        import keras   # pure keras
        from keras.backend.tensorflow_backend import set_session
        set_session(tf.Session(config=conf))

    learnFileRoot = os.path.splitext(learnFile)[0]

    En, A, Cl = readLearnFile(learnFile)
    if testFile != None:
        En_test, A_test, Cl_test = readLearnFile(testFile)
        totA = np.vstack((A, A_test))
        totCl = np.append(Cl, Cl_test)
    else:
        totA = A
        totCl = Cl

    with open(dP.spectral_range, 'ab') as f:
        f.write(pickle.dumps(En))

    print("  Total number of points per data:",En.size)
    print("  Number of learning labels: {0:d}\n".format(int(dP.numLabels)))
    
    if dP.regressor:
        Cl2 = np.copy(Cl)
        if testFile != None:
            Cl2_test = np.copy(Cl_test)
    else:
    
        #************************************
        # Label Encoding
        #************************************
        '''
        # sklearn preprocessing is only for single labels
        from sklearn import preprocessing
        le = preprocessing.LabelEncoder()
        totCl2 = le.fit_transform(totCl)
        Cl2 = le.transform(Cl)
        if testFile != None:
            Cl2_test = le.transform(Cl_test)
        '''
        le = MultiClassReductor()
        le.fit(np.unique(totCl, axis=0))
        Cl2 = le.transform(Cl)
    
        print("  Number unique classes (training): ", np.unique(Cl).size)
    
        if testFile != None:
            Cl2_test = le.transform(Cl_test)
            print("  Number unique classes (validation):", np.unique(Cl_test).size)
            print("  Number unique classes (total): ", np.unique(totCl).size)
            
        print("\n  Label Encoder saved in:", dP.model_le,"\n")
        with open(dP.model_le, 'ab') as f:
            f.write(pickle.dumps(le))

        #totCl2 = keras.utils.to_categorical(totCl2, num_classes=np.unique(totCl).size)
        Cl2 = keras.utils.to_categorical(Cl2, num_classes=np.unique(totCl).size+1)
        if testFile != None:
            Cl2_test = keras.utils.to_categorical(Cl2_test, num_classes=np.unique(totCl).size+1)

    #************************************
    # Training
    #************************************

    if dP.fullSizeBatch == True:
        dP.batch_size = A.shape[0]

    #************************************
    ### Define optimizer
    #************************************
    #optim = opt.SGD(lr=0.0001, decay=1e-6, momentum=0.9, nesterov=True)
    optim = keras.optimizers.Adam(lr=dP.l_rate, beta_1=0.9,
                    beta_2=0.999, epsilon=1e-08,
                    decay=dP.l_rdecay,
                    amsgrad=False)
    #************************************
    ### Build model
    #************************************
    model = keras.models.Sequential()
    for i in range(len(dP.HL)):
        model.add(keras.layers.Dense(dP.HL[i],
            activation = 'relu',
            input_dim=A.shape[1],
            kernel_regularizer=keras.regularizers.l2(dP.l2)))
        model.add(keras.layers.Dropout(dP.drop))

    if dP.regressor:
        model.add(keras.layers.Dense(1))
        model.compile(loss='mse',
        optimizer=optim,
        metrics=['mae'])
    else:
        model.add(keras.layers.Dense(np.unique(totCl).size+1, activation = 'softmax'))
        model.compile(loss='categorical_crossentropy',
            optimizer=optim,
            metrics=['accuracy'])

    tbLog = keras.callbacks.TensorBoard(log_dir=dP.tb_directory, histogram_freq=120,
            batch_size=dP.batch_size,
            write_graph=True, write_grads=True, write_images=True)
    tbLogs = [tbLog]
    
    model.summary()
    
    if testFile != None:
        log = model.fit(A, Cl2,
            epochs=dP.epochs,
            batch_size=dP.batch_size,
            callbacks = tbLogs,
            verbose=2,
            validation_data=(A_test, Cl2_test))
    else:
        log = model.fit(A, Cl2,
            epochs=dP.epochs,
            batch_size=dP.batch_size,
            callbacks = tbLogs,
            verbose=2,
	        validation_split=dP.cv_split)

    model.save(dP.model_name)
    keras.utils.plot_model(model, to_file=dP.model_png, show_shapes=True)
    model.summary()

    print('\n  =============================================')
    print('  \033[1mKeras MLP\033[0m - Model Configuration')
    print('  =============================================')

    print("  Training set file:",learnFile)
    print("  Data size:", A.shape,"\n")
    print("  Number of learning labels:",dP.numLabels)
    print("  Total number of points per data:",En.size)

    loss = np.asarray(log.history['loss'])
    val_loss = np.asarray(log.history['val_loss'])

    if dP.regressor:
        val_mae = np.asarray(log.history['val_mean_absolute_error'])
        printParam()
        print('\n  ==========================================================')
        print('  \033[1mKeras MLP - Regressor\033[0m - Training Summary')
        print('  ==========================================================')
        print("  \033[1mLoss\033[0m - Average: {0:.4f}; Min: {1:.4f}; Last: {2:.4f}".format(np.average(loss), np.amin(loss), loss[-1]))
        print('\n\n  ==========================================================')
        print('  \033[1mKeras MLP - Regressor \033[0m - Validation Summary')
        print('  ========================================================')
        print("  \033[1mLoss\033[0m - Average: {0:.4f}; Min: {1:.4f}; Last: {2:.4f}".format(np.average(val_loss), np.amin(val_loss), val_loss[-1]))
        print("  \033[1mMean Abs Err\033[0m - Average: {0:.4f}; Min: {1:.4f}; Last: {2:.4f}\n".format(np.average(val_mae), np.amin(val_mae), val_mae[-1]))
        print('  ========================================================')
        if testFile != None and dP.showValidPred:
            predictions = model.predict(A_test)
            print("  Real value | Predicted value | val_loss | val_mean_abs_err")
            print("  -----------------------------------------------------------")
            for i in range(0,len(predictions)):
                score = model.evaluate(np.array([A_test[i]]), np.array([Cl_test[i]]), batch_size=dP.batch_size, verbose = 0)
                print("  {0:.2f}\t\t| {1:.2f}\t\t| {2:.4f}\t| {3:.4f} ".format(Cl2_test[i],
                    predictions[i][0], score[0], score[1]))
            print('\n  ==========================================================\n')
    else:
        accuracy = np.asarray(log.history['acc'])
        val_acc = np.asarray(log.history['val_acc'])
        print("  Number unique classes (training): ", np.unique(Cl).size)
        if testFile != None:
            Cl2_test = le.transform(Cl_test)
            print("  Number unique classes (validation):", np.unique(Cl_test).size)
            print("  Number unique classes (total): ", np.unique(totCl).size)
        printParam()
        print('\n  ========================================================')
        print('  \033[1mKeras MLP - Classifier \033[0m - Training Summary')
        print('  ========================================================')
        print("\n  \033[1mAccuracy\033[0m - Average: {0:.2f}%; Max: {1:.2f}%; Last: {2:.2f}%".format(100*np.average(accuracy),
            100*np.amax(accuracy), 100*accuracy[-1]))
        print("  \033[1mLoss\033[0m - Average: {0:.4f}; Min: {1:.4f}; Last: {2:.4f}".format(np.average(loss), np.amin(loss), loss[-1]))
        print('\n\n  ========================================================')
        print('  \033[1mKeras MLP - Classifier \033[0m - Validation Summary')
        print('  ========================================================')
        print("\n  \033[1mAccuracy\033[0m - Average: {0:.2f}%; Max: {1:.2f}%; Last: {2:.2f}%".format(100*np.average(val_acc),
        100*np.amax(val_acc), 100*val_acc[-1]))
        print("  \033[1mLoss\033[0m - Average: {0:.4f}; Min: {1:.4f}; Last: {2:.4f}\n".format(np.average(val_loss), np.amin(val_loss), val_loss[-1]))
        print('  ========================================================')
        if testFile != None and dP.showValidPred:
            print("  Real class\t| Predicted class\t| Probability")
            print("  ---------------------------------------------------")
            predictions = model.predict(A_test)
            for i in range(predictions.shape[0]):
                predClass = np.argmax(predictions[i])
                predProb = round(100*predictions[i][predClass],2)
                predValue = le.inverse_transform(predClass)[0]
                realValue = Cl_test[i]
                print("  {0:.2f}\t\t| {1:.2f}\t\t\t| {2:.2f}".format(realValue, predValue, predProb))
            #print("\n  Validation - Loss: {0:.2f}; accuracy: {1:.2f}%".format(score[0], 100*score[1]))
            print('\n  ========================================================\n')

    if dP.plotWeightsFlag == True:
        plotWeights(En, A, model)

#************************************
# Prediction
#************************************
def predict(testFile):
    dP = Conf()
    if dP.useTFKeras:
        import tensorflow.keras as keras  #tf.keras
    else:
        import keras   # pure Keras
    
    model = keras.models.load_model(dP.modelName)

    try:
        R = readTestFile(testFile)
    except:
        print('\033[1m' + '\n Sample data file not found \n ' + '\033[0m')
        return

    if dP.regressor:
        predictions = model.predict(R).flatten()[0]
        print('\n  ========================================================')
        print('  \033[1mKeras MLP - Regressor\033[0m - Prediction')
        print('  ========================================================')
        predValue = predictions
        print('\033[1m\n  Predicted value (normalized) = {0:.2f}\033[0m\n'.format(predValue))
        print('  ========================================================\n')
        
    else:
        le = pickle.loads(open(dP.model_le, "rb").read())
        predictions = model.predict(R, verbose=0)
        pred_class = np.argmax(predictions)
        predProb = round(100*predictions[0][pred_class],2)
        rosterPred = np.where(predictions[0]>0.1)[0]
        print('\n  ========================================================')
        print('  \033[1mKeras MLP - Classifier\033[0m - Prediction')
        print('  ========================================================')

        if dP.numLabels == 1:
            if pred_class.size >0:
                predValue = le.inverse_transform(pred_class)[0]
            else:
                predValue = 0
            print('  Prediction\tProbability [%]')
            print('  -----------------------------')
            for i in range(len(predictions[0])-1):
                if predictions[0][i]>0.01:
                    print(' ',le.inverse_transform(i)[0],'\t\t',
                        str('{:.2f}'.format(100*predictions[0][i])))
            print('\033[1m\n  Predicted value = {0:.2f} (probability = {1:.2f}%)\033[0m\n'.format(predValue, predProb))
            print('  ========================================================\n')

        else:
            print('\n ==========================================')
            print('\033[1m' + ' Predicted value \033[0m(probability = ' + str(predProb) + '%)')
            print(' ==========================================\n')
            print("  1:", str(predValue[0]),"%")
            print("  2:",str(predValue[1]),"%")
            print("  3:",str((predValue[1]/0.5)*(100-99.2-.3)),"%\n")
            print(' ==========================================\n')

#************************************
# Batch Prediction
#************************************
def batchPredict():
    dP = Conf()
    if dP.useTFKeras:
        import tensorflow.keras as keras  #tf.keras
    else:
        import keras   # pure Keras

    model = keras.models.load_model(dP.modelName)

    predictions = np.zeros((0,0))
    fileName = []
    for file in glob.glob('*.txt'):
        R = readTestFile(file)
        try:
            predictions = np.vstack((predictions,model.predict(R).flatten()))
        except:
            predictions = np.array([model.predict(R).flatten()])
        fileName.append(file)

    if dP.regressor:
        summaryFile = np.array([['SpectraKeras_MLP','Regressor','',],['File name','Prediction','']])
        print('\n  ========================================================')
        print('  \033[1mKeras MLP - Regressor\033[0m - Prediction')
        print('  ========================================================')
        for i in range(predictions.shape[0]):
            predValue = predictions[i][0]
            print('  {0:s}:\033[1m\n   Predicted value = {1:.2f}\033[0m\n'.format(fileName[i],predValue))
            summaryFile = np.vstack((summaryFile,[fileName[i],predValue,'']))
        print('  ========================================================\n')

    else:
        le = pickle.loads(open(dP.model_le, "rb").read())
        summaryFile = np.array([['SpectraKeras_MLP','Classifier',''],['File name','Predicted Class', 'Probability']])
        print('\n  ========================================================')
        print('  \033[1mKeras MLP - Classifier\033[0m - Prediction')
        print('  ========================================================')
        for i in range(predictions.shape[0]):
            pred_class = np.argmax(predictions[i])
            predProb = round(100*predictions[0][pred_class],2)
            rosterPred = np.where(predictions[i][0]>0.1)[0]
        
            if pred_class.size >0:
                predValue = le.inverse_transform(pred_class)[0]
                print('  {0:s}:\033[1m\n   Predicted value = {1:.2f} (probability = {2:.2f}%)\033[0m\n'.format(fileName[i],predValue, predProb))
            else:
                predValue = 0
                print('  {0:s}:\033[1m\n   No predicted value (probability = {1:.2f}%)\033[0m\n'.format(fileName[i],predProb))
            summaryFile = np.vstack((summaryFile,[fileName[i], predValue,predProb]))
        print('  ========================================================\n')
    df = pd.DataFrame(summaryFile)
    df.to_csv(dP.summaryFileName, index=False, header=False)
    print(" Prediction summary saved in:",dP.summaryFileName,"\n")

#************************************
# Open Learning Data
#************************************
def readLearnFile(learnFile):
    print("\n  Opening learning file: ",learnFile)
    try:
        if os.path.splitext(learnFile)[1] == ".npy":
            M = np.load(learnFile)
        elif os.path.splitext(learnFile)[1] == ".h5":
            with h5py.File(learnFile, 'r') as hf:
                M = hf["M"][:]
        else:
            with open(learnFile, 'r') as f:
                M = np.loadtxt(f, unpack =False)
    except:
        print("\033[1m Learning file not found\033[0m")
        return

    dP = Conf()
    En = M[0,dP.numLabels:]
    A = M[1:,dP.numLabels:]
    
    if dP.normalize:
        norm = Normalizer()
        A = norm.transform_matrix(A)

    if dP.numLabels == 1:
        Cl = M[1:,0]
    else:
        Cl = M[1:,[0,dP.numLabels-1]]

    return En, A, Cl

#************************************
# Open Testing Data
#************************************
def readTestFile(testFile):

    with open(testFile, 'r') as f:
        print('\n  Opening sample data for prediction:\n  ',testFile)
        Rtot = np.loadtxt(f, unpack =True)
    R = preprocess(Rtot)
    return R

#****************************************************
# Check Energy Range and convert to fit training set
#****************************************************
def preprocess(Rtot):
    dP = Conf()
    En = pickle.loads(open(dP.spectral_range, "rb").read())
    R = np.array([Rtot[1,:]])
    Rx = np.array([Rtot[0,:]])
    
    if dP.normalize:
        norm = Normalizer()
        R = norm.transform_single(R)
    
    if(R.shape[1] != len(En)):
        print('  Rescaling x-axis from',str(R.shape[1]),'to',str(len(En)))
        R = np.interp(En, Rx[0], R[0])
        R = R.reshape(1,-1)

    return R

#************************************
# Print NN Info
#************************************
def printParam():
    dP = Conf()
    print('\n  ================================================')
    print('  \033[1mKeras MLP\033[0m - Parameters')
    print('  ================================================')
    print('  Optimizer:','Adam',
                '\n  Hidden layers:', dP.HL,
                '\n  Activation function:','relu',
                '\n  L2:',dP.l2,
                '\n  Dropout:', dP.drop,
                '\n  Learning rate:', dP.l_rate,
                '\n  Learning decay rate:', dP.l_rdecay)
    if dP.fullSizeBatch == True:
        print('  Batch size: full')
    else:
        print('  Batch size:', dP.batch_size)
    print('  Number of labels:', dP.numLabels)
    #print('  ================================================\n')

#************************************
# Open Learning Data
#************************************
def plotWeights(En, A, model):
    import matplotlib.pyplot as plt
    plt.figure(tight_layout=True)
    plotInd = 511
    for layer in model.layers:
        try:
            w_layer = layer.get_weights()[0]
            ax = plt.subplot(plotInd)
            newX = np.arange(En[0], En[-1], (En[-1]-En[0])/w_layer.shape[0])
            plt.plot(En, np.interp(En, newX, w_layer[:,0]), label=layer.get_config()['name'])
            plt.legend(loc='upper right')
            plt.setp(ax.get_xticklabels(), visible=False)
            plotInd +=1
        except:
            pass

    ax1 = plt.subplot(plotInd)
    ax1.plot(En, A[0], label='Sample data')

    plt.xlabel('Raman shift [1/cm]')
    plt.legend(loc='upper right')
    plt.savefig('keras_MLP_weights' + '.png', dpi = 160, format = 'png')  # Save plot

#************************************
# Lists the program usage
#************************************
def usage():
    print('\n Usage:\n')
    print(' Train (Random cross validation):')
    print('  python3 SpectraKeras_MLP.py -t <learningFile>\n')
    print(' Train (with external validation):')
    print('  python3 SpectraKeras_MLP.py -t <learningFile> <validationFile>\n')
    print(' Predict:')
    print('  python3 SpectraKeras_MLP.py -p <testFile>\n')
    print(' Batch predict:')
    print('  python3 SpectraKeras_MLP.py -b\n')
    print(' Requires python 3.x. Not compatible with python 2.x\n')

#************************************
# Main initialization routine
#************************************
if __name__ == "__main__":
    sys.exit(main())
