# mainly forking from notebook
# https://www.kaggle.com/johnfarrell/simple-rnn-with-keras-script
# http://jeffreyfossett.com/2014/04/25/tokenizing-raw-text-in-python.html
# encoding=utf8  
import sys  
#reload(sys)  
#sys.setdefaultencoding('utf8')
import os, math, gc, time, random

from datetime import datetime
from csv import DictReader
from math import exp, log, sqrt
start_time = time.time()
import numpy as np
from numba import jit
from collections import Counter
from scipy.sparse import csr_matrix, hstack
import nltk
from nltk.tokenize import ToktokTokenizer
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import tensorflow as tf
from keras.preprocessing.text import Tokenizer
def _get_session():
    config = tf.ConfigProto()
    config.gpu_options.allow_growth = True
    return tf.Session(config=config)
_get_session()
from keras.preprocessing.sequence import pad_sequences
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from keras.layers import Input, Dropout, Dense, BatchNormalization, \
    Activation, concatenate, GRU, Embedding, Flatten, Bidirectional, \
    MaxPooling1D, Conv1D, Add, CuDNNLSTM, CuDNNGRU, Reshape
from keras.models import Model
from keras.callbacks import ModelCheckpoint, Callback, EarlyStopping#, TensorBoard
from keras import backend as K
from keras import optimizers
from keras import initializers
from keras.utils import plot_model
import warnings
warnings.simplefilter(action='ignore')

os.chdir('/home/darragh/mercari/data')
#os.chdir('/Users/dhanley2/Documents/mercari/data')


train = pd.read_csv('../data/train.tsv', sep='\t', encoding='utf-8')
test = pd.read_csv('../data/test.tsv', sep='\t', encoding='utf-8')

train['target'] = np.log1p(train['price'])
print(train.shape)
print(test.shape)
print('[{}] Finished scaling test set...'.format(time.time() - start_time))


#HANDLE MISSING VALUES
print("Handling missing values...")
def handle_missing(dataset):
    missing_string = "_missing_"
    dataset.category_name.fillna(value=missing_string, inplace=True)
    dataset.brand_name.fillna(value=missing_string, inplace=True)
    dataset.item_description.fillna(value=missing_string, inplace=True)
    return (dataset)

train = handle_missing(train)
test = handle_missing(test)
print(train.shape)
print(test.shape)
print('[{}] Finished handling missing data...'.format(time.time() - start_time))

pd.set_option('display.height', 500)
pd.set_option('display.max_rows', 500)

#PROCESS CATEGORICAL DATA
from sklearn.preprocessing import LabelEncoder, MinMaxScaler, StandardScaler
print("Handling categorical variables...")
le = LabelEncoder()

le.fit(np.hstack([train.category_name, test.category_name]))
train['category'] = le.transform(train.category_name)
test['category'] = le.transform(test.category_name)


hi_brand_cts = train['brand_name'].value_counts()
hi_brand_cts = hi_brand_cts[hi_brand_cts>5].index.values
train.brand_name[~train.brand_name.isin(hi_brand_cts)] = '_lo_count_'
test.brand_name[~test.brand_name.isin(hi_brand_cts)] = '_lo_count_'
le.fit(np.hstack([train.brand_name, test.brand_name]))
train['brand'] = le.transform(train.brand_name)
test['brand'] = le.transform(test.brand_name)
del le, train['brand_name'], test['brand_name']

# Replace the category slash
test["category_name_split"] = test["category_name"].str.replace(' ', '_')
train["category_name_split"] = train["category_name"].str.replace(' ', '_')
test["category_name_split"] = test["category_name_split"].str.replace('/', ' ')
train["category_name_split"] = train["category_name_split"].str.replace('/', ' ')
train.head()
print('[{}] Finished PROCESSING CATEGORICAL DATA...'.format(time.time() - start_time))


toktok = ToktokTokenizer()
train['name_token'] = [" ".join(toktok.tokenize(sent)) for sent in train['name'].str.lower().tolist()]
test['name_token'] = [" ".join(toktok.tokenize(sent)) for sent in test['name'].str.lower().tolist()]
print('[{}] Finished Tokenizing text...'.format(time.time() - start_time))


#PROCESS TEXT: RAW
print("Text to seq process...")
print("   Fitting tokenizer...")


import re
rgx = re.compile('[%s]' % '!"#%&()*+,-./:;<=>?@[\\]^_`{|}~\t\n')   
                 
@jit
def myTokenizerFitJit(strls, max_words = 25000, filt = True):
    list_=[]
    for sent in strls:
        if filt:
            sent = rgx.sub('', sent)
        for s in sent.split(' '):
            list_.append(s)
    return Counter(list_).most_common(max_words)

def myTokenizerFit(strls, max_words = 25000):
    mc = myTokenizerFitJit(strls, max_words = 25000)
    return dict((i, c+1) for (c, (i, ii)) in enumerate(mc))  


@jit
def fit_sequence(str_, tkn_, filt = True):
    labels = []
    for sent in str_:
        if filt:
            sent = rgx.sub('', sent)
        tk = []
        for i in sent.split(' '):
            if i in tkn_:
                tk.append(tkn_[i])
        labels.append(tk)
    return labels

tok_raw_cat = myTokenizerFit(train.category_name_split.str.lower().unique(), max_words = 200)
tok_raw_nam = myTokenizerFit(train.name.str.lower().unique(), max_words = 25000)
tok_raw_dsc = myTokenizerFit(train.item_description.str.lower().unique(), max_words = 25000)
tok_raw_ntk = myTokenizerFit(train.name_token.str.lower().unique(), max_words = 50000)
print('[{}] Finished FITTING TEXT DATA...'.format(time.time() - start_time))
print("   Transforming text to seq...")
train["seq_category_name_split"] =     fit_sequence(train.category_name_split.str.lower(), tok_raw_cat)
test["seq_category_name_split"] =      fit_sequence(test.category_name_split.str.lower(), tok_raw_cat)
train["seq_item_description"] =        fit_sequence(train.item_description.str.lower(), tok_raw_dsc)
test["seq_item_description"] =         fit_sequence(test.item_description.str.lower(), tok_raw_dsc)
train["seq_name"] =                    fit_sequence(train.name.str.lower(), tok_raw_nam)
test["seq_name"] =                     fit_sequence(test.name.str.lower(), tok_raw_nam)
train["seq_name_token"] =              fit_sequence(train.name_token.str.lower(), tok_raw_ntk, filt = False)
test["seq_name_token"] =               fit_sequence(test.name_token.str.lower(), tok_raw_ntk, filt = False)
print('[{}] Finished PROCESSING TEXT DATA...'.format(time.time() - start_time))
train.head()
#EXTRACT DEVELOPTMENT TEST
dtrain, dvalid = train_test_split(train, random_state=233, train_size=0.90)
print(dtrain.shape)
print(dvalid.shape)


#EMBEDDINGS MAX VALUE
MAX_CAT = max(tok_raw_cat.values())+1
MAX_NAM = max(tok_raw_nam.values())+1
MAX_NTK = max(tok_raw_ntk.values())+1
MAX_DSC = max(tok_raw_dsc.values())+1
MAX_CATEGORY = np.max([train.category.max(), test.category.max()])+1
MAX_BRAND = np.max([train.brand.max(), test.brand.max()])+1
MAX_CONDITION = np.max([train.item_condition_id.max(), 
                        test.item_condition_id.max()])+1


print('[{}] Finished EMBEDDINGS MAX VALUE...'.format(time.time() - start_time)) 

# Sort the data on the length of the descriptions which will make it quicker
# for the variable length GRU


def get_keras_data(dataset):
    X = {
        'name': pad_sequences(dataset.seq_name, 
                              maxlen=max([len(l) for l in dataset.seq_name]))
        ,'ntk': pad_sequences(dataset.seq_name, 
                              maxlen=max([len(l) for l in dataset.seq_name_token]))
        ,'item_desc': pad_sequences(dataset.seq_item_description, 
                              maxlen=max([len(l) for l in dataset.seq_item_description]))
        ,'brand': np.array(dataset.brand)
        ,'category': np.array(dataset.category)
        ,'category_name_split': pad_sequences(dataset.seq_category_name_split, 
                              maxlen=max([len(l) for l in dataset.seq_category_name_split]))
        ,'item_condition': np.array(dataset.item_condition_id)
        ,'num_vars': np.array(dataset[["shipping"]])
    }
    return X   

def eval_model(y_true, val_preds):
    val_preds = np.expm1(val_preds)
    y_pred = val_preds[:, 0]
    v_rmsle = rmsle(y_true, y_pred)
    print("RMSLE error on dev test: "+str(v_rmsle))
    return v_rmsle

def len_argsort(seq):
	return sorted(range(len(seq)), key=lambda x: len(seq[x]))

def map_sort(seq1, seq2):
	return sorted(range(len(seq1)), key=lambda x: len(seq1[x])*100+len(seq2[x]))
    
def reset_data(dt, bsize):
    max_step = dt.shape[0]
    n_batches = int(np.ceil(max_step*1. / float(bsize)))
    batch_steps = np.array(random.sample(range(n_batches), n_batches))
    #sorted_ix = np.array(len_argsort(dt["seq_item_description"].tolist()))
    sorted_ix = np.array(map_sort(dt["seq_item_description"].tolist(), dt["seq_name_token"].tolist()))
    dt.reset_index(drop=True, inplace = True)  
    return max_step, batch_steps, sorted_ix, dt

def trn_generator(dt, y, bsize):
    while True:
        max_step, batch_steps, sorted_ix, dt = reset_data(dt, bsize)
        for batch in batch_steps:
            from_ = batch*bsize
            to_   = min((batch+1)*bsize, max_step)
            ix_   = sorted_ix[from_:to_]
            Xbatch = dt.iloc[ix_]
            Xbatch = get_keras_data(Xbatch)
            ybatch = dt.target.iloc[ix_]
            yield Xbatch, ybatch

def val_generator(dt, y, bsize):
    while 1:
        max_step, batch_steps, sorted_ix, dt = reset_data(dt, bsize)
        for batch in batch_steps:
            from_ = batch*bsize
            to_   = min((batch+1)*bsize, max_step)
            ix_   = sorted_ix[from_:to_]
            Xbatch = dt.iloc[ix_]
            Xbatch = get_keras_data(Xbatch)
            ybatch = dt.target.iloc[ix_]
            yield Xbatch, ybatch

def tst_generator(dt, bsize):
    while 1:
        for batch in range(int(np.ceil(dt.shape[0]*1./bsize))):
        #for batch in range(dt.shape[0]/bsize+1):
            from_ = batch*bsize
            to_   = min((batch+1)*bsize, dt.shape[0])
            Xbatch = dt.iloc[from_:to_]
            Xbatch = get_keras_data(Xbatch)
            yield Xbatch

#KERAS MODEL DEFINITION
def rmsle(y, y_pred):
    assert len(y) == len(y_pred)
    to_sum = [(math.log(y_pred[i] + 1) - math.log(y[i] + 1)) ** 2.0 \
              for i, pred in enumerate(y_pred)]
    return (sum(to_sum) * (1.0/len(y))) ** 0.5

dr = 0.1

from keras.layers import GlobalMaxPooling1D


def get_model():

    ##Inputs
    name = Input(shape=[None], name="name")
    ntk = Input(shape=[None], name="ntk")
    item_desc = Input(shape=[None], name="item_desc")
    category_name_split = Input(shape=[None], name="category_name_split")
    brand = Input(shape=[1], name="brand")
    item_condition = Input(shape=[1], name="item_condition")
    num_vars = Input(shape=[1], name="num_vars")
    
    #Embeddings layers
    emb_size = 60
    emb_name                = Embedding(MAX_NAM, emb_size//2)(name) 
    emb_ntk                 = Embedding(MAX_NTK, emb_size//2)(ntk) 
    emb_item_desc           = Embedding(MAX_DSC, emb_size)(item_desc) 
    emb_category_name_split = Embedding(MAX_CAT, emb_size//3)(category_name_split) 
    emb_brand               = Embedding(MAX_BRAND, 8)(brand)
    emb_item_condition      = Embedding(MAX_CONDITION, 5)(item_condition)
    
    rnn_layer1 = GRU(16, recurrent_dropout=0.0) (emb_item_desc)
    rnn_layer2 = GRU(8, recurrent_dropout=0.0) (emb_category_name_split)
    rnn_layer3 = GRU(8, recurrent_dropout=0.0) (emb_name)
    rnn_layer4 = GRU(8, recurrent_dropout=0.0) (emb_ntk)
    
    #main layer
    main_l = concatenate([
        Flatten() (emb_brand)
        , Flatten() (emb_item_condition)
        , rnn_layer1
        , rnn_layer2
        , rnn_layer3
        , rnn_layer4
        , num_vars
    ])
    main_l = Dropout(dr)(Dense(128,activation='relu') (main_l))
    main_l = Dropout(dr)(Dense(64,activation='relu') (main_l))
    
    #output
    output = Dense(1,activation="linear") (main_l)
    
    #model
    model = Model([name, brand, ntk, item_desc
                   , category_name_split #,category
                   , item_condition, num_vars], output)
    optimizer = optimizers.Adam()
    model.compile(loss='mse', 
                  optimizer=optimizer)
    return model

print('[{}] Finished DEFINING MODEL...'.format(time.time() - start_time))

epochs = 3
batchSize = 512 * 4
steps = (dtrain.shape[0]/batchSize+1)*epochs
lr_init, lr_fin = 0.013, 0.007
lr_decay  = (lr_init - lr_fin)/steps
model = get_model()
K.set_value(model.optimizer.lr, lr_init)
K.set_value(model.optimizer.decay, lr_decay)

history = model.fit_generator(
                    trn_generator(dtrain, dtrain.target, batchSize)
                    , epochs=epochs
                    , max_queue_size=1
                    , steps_per_epoch = int(np.ceil(dtrain.shape[0]*1./batchSize))
                    , validation_data = val_generator(dvalid, dvalid.target, batchSize)
                    , validation_steps = int(np.ceil(dvalid.shape[0]*1./batchSize))
                    , verbose=1
                    )
val_sorted_ix = np.array(map_sort(dvalid["seq_item_description"].tolist(), dvalid["seq_name_token"].tolist()))
y_pred = model.predict_generator(tst_generator(dvalid.iloc[val_sorted_ix], batchSize)
                    , steps = int(np.ceil(dvalid.shape[0]*1./batchSize))
                    , max_queue_size=1 
                    , verbose=1)[val_sorted_ix.argsort()]
print "Epoch %s rmsle %s"%(epochs, eval_model(dvalid.price.values, y_pred))


'''
Start the lightgbm
'''

import lightgbm as lgb

def col2sparse(var, max_col):
    row = []
    col = []
    data = []
    for c, l_ in enumerate(var):
        n_ = len(l_)
        row += [c]*n_
        col += l_
        data += [1]*n_
    shape_ = (len(var), max_col+1)
    return csr_matrix((data, (row, col)), shape=shape_)

llcols = [("seq_category_name_split", MAX_CAT), ("seq_item_description", MAX_DSC), \
          ("seq_name", MAX_NAM), ("seq_name_token", MAX_NTK)]
lcols = ["brand", "item_condition_id", "shipping", "category"]

spmatval = hstack([col2sparse(dvalid[c_].tolist(), max_col = max_val) for (c_, max_val) in llcols] + \
                  [col2sparse([[l] for l in dvalid[c_].tolist()], \
                               max_col = max(dvalid[c_].tolist())+1) for c_ in lcols]).tocsr().astype(np.float32)
spmattrn = hstack([col2sparse(dtrain[c_].tolist(), max_col = max_val) for (c_, max_val) in llcols] + \
                  [col2sparse([[l] for l in dtrain[c_].tolist()], \
                               max_col = max(dtrain[c_].tolist())+1) for c_ in lcols]).tocsr().astype(np.float32)

spmatval = hstack([spmatval, csr_matrix(spmatval.sum(axis=1))])
spmattrn = hstack([spmattrn, csr_matrix(spmattrn.sum(axis=1))])


d_train = lgb.Dataset(spmattrn, label=dtrain.target)#, max_bin=8192)
d_valid = lgb.Dataset(spmatval, label=dvalid.target)#, max_bin=8192)
watchlist = [d_train, d_valid]

params = {
    'learning_rate': 0.76,
    'application': 'regression',
    'max_depth': 3,
    'num_leaves': 99,
    'verbosity': 1,#-1,
    'metric': 'RMSE',
    'nthread': 4
}

model = lgb.train(params, train_set=d_train, num_boost_round=7500, valid_sets=watchlist, \
early_stopping_rounds=500, verbose_eval=10) 
#[4000]  training's rmse: 0.427902       valid_1's rmse: 0.45261
#[7080]  training's rmse: 0.4108 valid_1's rmse: 0.447027
y_predlgb = model.predict(spmatval)
y_predlgb = np.expand_dims(y_predlgb, 1)
print("LGB trees %s rmsle %s"%(model.best_iteration, eval_model(dvalid.price.values, y_predlgb)))
# LGB trees 0 rmsle 0.446724284216

y_predbag = 0.5*y_predlgb+0.5*y_pred
print("Bagged rmsle %s"%(eval_model(dvalid.price.values, y_predbag)))
# Bagged rmsle 0.428013403748


'''
Leak
'''
strcols = ["name", "item_condition_id", "category_name", "shipping", \
           "category_name_split"]

@jit
def hashList(ll):
    for k, v in ll.iteritems():
        if k == 'item_description':
            v = v[:20]
    ll = [abs(hash(l))%(2**22) for l in ll.values]
    return "_".join(map(str, ll))

dvalid["leak"] = [ hashList(lv_) for (c, lv_)  in dvalid[strcols].iterrows()]
dtrain["leak"] = [ hashList(lv_) for (c, lv_)  in dtrain[strcols].iterrows()]
means_dict = pd.groupby(dtrain[["leak", "target"]], "leak").mean().to_dict()[u'target']

leak = np.array([means_dict[l] if l in means_dict else np.NaN for l in dvalid["leak"].tolist()])
y_predbaglk = 0.5*y_predlgb+0.5*y_pred
ix = (~np.isnan(leak)) & (dvalid["name"].str.len().values>30)
y_predbaglk[ix] = np.expand_dims(leak[ix],1)
print("Bagged rmsle %s"%(eval_model(dvalid.price.values, y_predbaglk)))



'''
y_pred = model.predict_generator(tst_generator(test, batchSize), 
                         steps = test.shape[0]/batchSize+1, 
                         verbose=1)
    

    np.histogram(y_pred)
    np.histogram( dvalid.target[val_sorted_ix])


print('[{}] Finished FITTING MODEL...'.format(time.time() - start_time))

#CREATE PREDICTIONS
preds = model.predict(X_test, batch_size=BATCH_SIZE)
preds = np.expm1(preds)
print('[{}] Finished predicting test set...'.format(time.time() - start_time))
submission = test[["test_id"]][:test_len]
submission["price"] = preds[:test_len]
submission.to_csv("./myNN"+log_subdir+"_{:.6}.csv".format(v_rmsle), index=False)
print('[{}] Finished submission...'.format(time.time() - start_time))
'''