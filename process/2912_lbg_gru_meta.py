# coding: utf-8

# mainly forking from notebook
# https://www.kaggle.com/johnfarrell/simple-rnn-with-keras-script
# http://jeffreyfossett.com/2014/04/25/tokenizing-raw-text-in-python.html
# encoding=utf8  
import lightgbm as lgb
import sys  
#reload(sys)  
#sys.setdefaultencoding('utf8')
import os, math, gc, time, random
start_time = time.time()
import numpy as np
from numba import jit
from collections import Counter
from scipy.sparse import csr_matrix, hstack
import nltk, re
from nltk.tokenize import ToktokTokenizer
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import tensorflow as tf
from keras.preprocessing.text import Tokenizer
import multiprocessing as mp
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
glove_file = '../feat/glove.6B.50d.txt'

train['target'] = np.log1p(train['price'])
print(train.shape)
print(test.shape)
print('[{}] Finished scaling test set...'.format(time.time() - start_time))


emojis = re.compile( 
    u"([^\u0101-\ufffd])"  
    u"([^\x96-\xfc])" 
    "+", flags=re.UNICODE)
asterix = re.compile('[%s]' % '!"#%&()*,-./:;<=>?@[\\]^_`{|}~\t\n')   
#print(special_pattern.sub(r'', text)) # no emoji

#sent = test.iloc[23]

@jit
def count_grammar(sent):
    counter = []
    for col in [0,1]:
        if sent[col]!=sent[col]:
            sent[col]=''
        counter.append(len(sent[col].split(' ')))
        counter.append(len(sent[col]))
        counter.append(len(re.findall(r'[A-Z]',sent[col])))
        counter.append(len(re.findall(r'[0-9]',sent[col])))
        counter.append(len(re.findall(asterix,sent[col])))
        counter.append(len(re.findall(emojis,sent[col])))
    return counter

def make_feat():
    pool = mp.Pool(processes=4)
    trnfeat = np.array(pool.map(count_grammar, train[['item_description', 'name']].values), dtype=np.float16)
    tstfeat = np.array(pool.map(count_grammar, test[['item_description', 'name']].values), dtype=np.float16)
    pool.close
    
    trnfeat = np.log1p(trnfeat)
    tstfeat = np.log1p(tstfeat)
    max_feat = trnfeat.max(axis=0)
    trnfeat /= max_feat
    tstfeat /= max_feat
    return trnfeat.tolist(), tstfeat.tolist()

train['lost_features'], test['lost_features'] = make_feat()

print('[{}] Finished creating features...'.format(time.time() - start_time))


print("Manual string correction...")
tech_mapper = {
               'unblocked' : 'unlocked',
               'ipad3' : ' ipad3 ',
               'ipad2' : ' ipad2 ',
               'ipad1' : ' ipad1 ',
               'ipad 3' : ' ipad3 ',
               'ipad 2' : ' ipad2 ',
               'ipad 1' : ' ipad1 ',
               '8 gb'     : ' 8gb ',
               '16 gb'    : ' 16gb ',
               '64 gb'    : ' 64gb ',
               '256 gb'   : ' 256gb ',
               '500 gb'   : ' 500gb ',
               '32 gb'    : ' 32gb ',
               'bnwt'     : 'brand new with tags',
               'nwt'      : 'new with tags',
               'bnwot'    : 'brand new without tags',
               'bnwob'    : 'brand new without box',
               'nwot'     : 'new without tags',
               'bnip'     : 'brand new in packet',
               'nip'      : 'new in packet',
               'bnib'     : 'brand new in box',
               'nib'      : 'new in box',
               'mib'      : 'mint in box',
               'mwob:'    : 'mint without box',
               'mip'      : 'mint in packet',
               'mwop'     : 'mint without packet',
               } 

def replace_maps(sent):
    if sent!=sent:
        return sent
    for k, v in tech_mapper.items():
        sent = sent.replace(k, v)
    return sent
import multiprocessing as mp
pool = mp.Pool(processes=4)
for col in ['name', 'item_description']:
    train[col] = train[col].str.lower()
    test[col] = test[col].str.lower().tolist()
    train[col] = pool.map(replace_maps, train[col].values)
    test[col] = pool.map(replace_maps, test[col].values)
pool.close
print('[{}] Finished replacing text...'.format(time.time() - start_time))


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

from sklearn.preprocessing import LabelEncoder, MinMaxScaler, StandardScaler
print("Handling categorical variables...")
le = LabelEncoder()

le.fit(np.hstack([train.category_name, test.category_name]))
train['category'] = le.transform(train.category_name)
test['category'] = le.transform(test.category_name)

hi_brand_cts = train['brand_name'].value_counts()
hi_brand_cts = hi_brand_cts[hi_brand_cts>2].index.values
train.brand_name[~train.brand_name.isin(hi_brand_cts)] = '_lo_count_'
test.brand_name[~test.brand_name.isin(hi_brand_cts)] = '_lo_count_'
le.fit(np.hstack([train.brand_name, test.brand_name]))
train['brand'] = le.transform(train.brand_name)
test['brand'] = le.transform(test.brand_name)
del le


print("Remove bogus characters...")
@jit
def get_characters():
    characters = set()
    for sent in train.name.unique():
        for s in sent:
            characters.add(s)
    return characters
all_chars = sorted(list(get_characters()))
"".join(all_chars)


#text = u'This dog -- \uc758\uc774\uc8fd\ud55c\ud589\ud654\uf8ff\ufe0e -- \x96\xa1\xa2\xa3\xa4\xa5\xa6\xa7\xa9'
#print(text) # with emoji
# https://stackoverflow.com/questions/33404752/removing-emojis-from-a-string-in-python
special_pattern = re.compile( 
    u"([\u0101-\ufffd])|"  
    u"([\x96-\xfc])" 
    "+", flags=re.UNICODE)
#print(special_pattern.sub(r'', text)) # no emoji

def remove_special(sent):
    if sent != sent:
        return sent
    return (special_pattern.sub(r' ', sent)) 

import multiprocessing as mp
pool = mp.Pool(processes=4)
for col in ["item_description", "name", "brand_name"]:
    print("Clean special characters from " + col)
    #train[col] = [(special_pattern.sub(r' ', sent)) if sent == sent else sent for sent in train[col].values]
    #test[col] = [(special_pattern.sub(r' ', sent)) if sent == sent else sent for sent in test[col].values]
    train[col] = pool.map(remove_special, train[col].values)
    test[col] =  pool.map(remove_special, test[col].values)
pool.close

print('[{}] Finished remove bogus characters...'.format(time.time() - start_time))


# Replace the category slash
test["category_name_split"] = test["category_name"].str.replace(' ', '_')
train["category_name_split"] = train["category_name"].str.replace(' ', '_')
test["category_name_split"] = test["category_name_split"].str.replace('/', ' ')
train["category_name_split"] = train["category_name_split"].str.replace('/', ' ')
train.head()
print('[{}] Finished PROCESSING CATEGORICAL DATA...'.format(time.time() - start_time))

from nltk.stem import PorterStemmer
#porter.stem(word)

toktok = ToktokTokenizer()
porter = PorterStemmer()
tokSentMap = {}
def tokSent(sent):
    sent = sent.replace('/', ' ')
    return " ".join(toktok.tokenize(rgx.sub('', sent)))

rgx = re.compile('[%s]' % '!"#%&()*,-./:;<=>?@[\\]^_`{|}~\t\n')   

pool = mp.Pool(processes=4)
train['description_token']      = pool.map(tokSent, train['item_description'].str.lower().tolist())
test ['description_token']      = pool.map(tokSent, test ['item_description'].str.lower().tolist())
train['name_token']             = pool.map(tokSent, train['name'].str.lower().tolist())
test ['name_token']             = pool.map(tokSent, test ['name'].str.lower().tolist())
train['category_token']         = pool.map(tokSent, train['category_name'].str.lower().tolist())
test ['category_token']         = pool.map(tokSent, test ['category_name'].str.lower().tolist())
train['brand_token']            = pool.map(tokSent, train['brand_name'].str.lower().tolist())
test ['brand_token']            = pool.map(tokSent, test ['brand_name'].str.lower().tolist())
print('[{}] Finished Tokenizing text...'.format(time.time() - start_time))
pool.close

#np.sort(train['category_token'].unique()).tolist()


'''
New parts
'''
@jit
def list_flatten(var):
    list_ = []
    for sent_ in var:
        list_ += sent_.split(' ')
    return Counter(list_)

wordlist = []
for col in ['name_token', 'category_token', 'brand_token']:
    for dt in train, test:
        flat_counter = list_flatten(dt[[col]].values[:,0])
        wordlist += [k for (k, v) in flat_counter.items() if v>3]
        wordlist = list(set(wordlist))
wordlist = set(wordlist)

embeddings_matrix = []
embedding_map = {}
#f = open('../feat/wiki.en.vec')
f = open(glove_file)
counter = 0
for line in f:
    values = line.split()
    word = values[0]
    if word not in wordlist:
        continue
    #coefs = np.asarray(values[1:], dtype='float32')
    embedding_map[word] = counter
    embeddings_matrix.append(values[1:])
    counter += 1
    if (counter % 10000 == 0) and (counter != 0):
        print('Found %s word vectors.' % counter)
f.close()
print('Found %s word vectors.' % counter)

embeddings_matrix = np.array(embeddings_matrix, dtype='float32')

# Get the dot product
def posn_to_sparse(dt, embedding_map):
    sprow = []
    spcol = []
    spdata = []
    for c, (nm, ct, bt) in enumerate(zip(dt['name_token'].values,
                               dt['category_token'].values,
                               dt['brand_token'].values)):
        sent = " ".join([nm, ct, bt])
        ids = [embedding_map[s] for s in sent.split(' ') if s in embedding_map]
        n_ = len(ids)
        sprow += [c]*n_
        spcol += ids
        spdata += [1]*n_    
    shape_ = (dt.shape[0], len(embedding_map.keys())) 
    dt_ids = csr_matrix((spdata, (sprow, spcol)), shape=shape_)
    return dt_ids

from nltk.stem.lancaster import LancasterStemmer
lancaster_stemmer = LancasterStemmer()
from nltk.corpus import stopwords
stopWords = set(stopwords.words('english'))
stemdict = {}      

@jit
def myTokenizerFitJit(strls, stem, filt = True):
    list_=[]
    #stemdict = {}
    for sent in strls:
        if filt:
            sent = rgx.sub(' ', sent)
        for s in sent.split(' '):
            if s!= '':
                if stem:
                    if s not in stemdict:
                        stemdict[s] = lancaster_stemmer.stem(s)
                    s = stemdict[s]
                    if s not in stopWords:
                        list_.append(s)
                else:
                    list_.append(s)
    return Counter(list_)

def myTokenizerFit(strls, stem, max_words = 35000, cutoff=30):
    mc = myTokenizerFitJit(strls, stem)
    mc = [(k,v)  for (k, v) in mc.items() if v > cutoff]
    return dict((i, c+1) for (c, (i, ii)) in enumerate(mc))  

@jit
def fit_sequence(str_, tkn_, stem, filt = True):
    labels = []
    #stemdict = {}
    for sent in str_:
        if filt:
            sent = rgx.sub(' ', sent)
        tk = []
        for i in sent.split(' '):
            if stem:
                if i not in stemdict:
                    stemdict[i] = lancaster_stemmer.stem(i)
                i = stemdict[i]

            if i in tkn_:
                if i != '':
                    tk.append(tkn_[i])
        labels.append(tk)
    return labels

'''
@jit
def fit_sequence_check(str_, tkn_, filt = True):
    labels = []
    for sent in str_:
        if filt:
            sent = rgx.sub(' ', sent)
        return [s for s in sent.split(' ') if s!= '']

sent= ["freeship***coach wristlet-bnwot"]
print(fit_sequence(sent , tok_raw_nam))
print(fit_sequence_check(sent , tok_raw_nam))
'''


tok_raw_cat = myTokenizerFit(train.category_name_split.str.lower().unique(), stem=False, cutoff=5)
#tok_raw_cat = myTokenizerFit(train.category_token.str.lower().unique(), max_words = 800)
tok_raw_nam = myTokenizerFit(train.name.str.lower().unique(), max_words = 25000, stem=False, cutoff=5)
#tok_raw_dsc = myTokenizerFit(train.item_description.str.lower().unique(), max_words = 25000)
tok_raw_dsc = myTokenizerFit(train.description_token.str.lower().unique(), stem=False)
tok_raw_ntk = myTokenizerFit(train.name_token.str.lower().unique(), stem=False)
#tok_raw_dst = myTokenizerFit(train.description_token.str.lower().unique(), stem=True, max_words = 25000)
tok_raw_nst = myTokenizerFit(train.name_token.str.lower().unique(), stem=True)
print('[{}] Finished FITTING TEXT DATA...'.format(time.time() - start_time))    
print("   Transforming text to seq...")
train["seq_category_name_split"] =     fit_sequence(train.category_name_split.str.lower(), tok_raw_cat, stem=False)
test["seq_category_name_split"] =      fit_sequence(test.category_name_split.str.lower(), tok_raw_cat, stem=False)
#train["seq_category_name_split"] =     fit_sequence(train.category_token.str.lower(), tok_raw_cat)
#test["seq_category_name_split"] =      fit_sequence(test.category_token.str.lower(), tok_raw_cat)
#train["seq_item_description"] =        fit_sequence(train.item_description.str.lower(), tok_raw_dsc)
#test["seq_item_description"] =         fit_sequence(test.item_description.str.lower(), tok_raw_dsc)
train["seq_item_description"] =        fit_sequence(train.description_token.str.lower(), tok_raw_dsc, stem=False)
test["seq_item_description"] =         fit_sequence(test.description_token.str.lower(), tok_raw_dsc, stem=False)
train["seq_name"] =                    fit_sequence(train.name.str.lower(), tok_raw_nam, stem=False)
test["seq_name"] =                     fit_sequence(test.name.str.lower(), tok_raw_nam, stem=False)
train["seq_name_token"] =              fit_sequence(train.name_token.str.lower(), tok_raw_ntk, filt = False, stem=False)
test["seq_name_token"] =               fit_sequence(test.name_token.str.lower(), tok_raw_ntk, filt = False, stem=False)
#train["seq_item_description_stem"] =   fit_sequence(train.description_token.str.lower(), tok_raw_dst, stem=True)
#test["seq_item_description_stem"] =    fit_sequence(test.description_token.str.lower(), tok_raw_dst, stem=True)
train["seq_name_token_stem"] =         fit_sequence(train.name_token.str.lower(), tok_raw_nst, filt = False, stem=True)
test["seq_name_token_stem"] =          fit_sequence(test.name_token.str.lower(), tok_raw_nst, filt = False, stem=True)
print('[{}] Finished PROCESSING TEXT DATA...'.format(time.time() - start_time))
train.head()
#EXTRACT DEVELOPTMENT TEST

print('[{}] Embeddings loaded...'.format(time.time() - start_time))
dtrain, dvalid = train_test_split(train, random_state=233, train_size=0.90)

dtrain_ids = posn_to_sparse(dtrain, embedding_map)
dvalid_ids = posn_to_sparse(dvalid, embedding_map)
test_ids  = posn_to_sparse(test, embedding_map)

# Get the dense layer input of the text
densetrn = dtrain_ids.dot(embeddings_matrix)#.todense()
denseval = dvalid_ids.dot(embeddings_matrix)#.todense()
densetst = test_ids.dot(embeddings_matrix)#.todense()
densetst
mean_, sd_ = densetrn.mean(), densetrn.std()
densetrn -= mean_
denseval -= mean_
densetst -= mean_
densetrn /= sd_
denseval /= sd_
densetst /= sd_

print(dtrain.shape)
print(densetrn.shape)

#PROCESS TEXT: RAW
print("Text to seq process...")
print("   Fitting tokenizer...")

#EMBEDDINGS MAX VALUE
MAX_CAT = max(tok_raw_cat.values())+1
MAX_NAM = max(tok_raw_nam.values())+1
MAX_NTK = max(tok_raw_ntk.values())+1
MAX_DSC = max(tok_raw_dsc.values())+1
#MAX_DST = max(tok_raw_dst.values())+1
MAX_NST = max(tok_raw_nst.values())+1
MAX_CATEGORY = np.max([train.category.max(), test.category.max()])+1
MAX_BRAND = np.max([train.brand.max(), test.brand.max()])+1
MAX_CONDITION = np.max([train.item_condition_id.max(), 
                        test.item_condition_id.max()])+1
    
print(MAX_CAT,MAX_NAM, MAX_NTK, MAX_DSC,MAX_NST,MAX_CATEGORY,MAX_BRAND,MAX_CONDITION)
    


def get_keras_data(dataset):
    X = {
        'name': pad_sequences(dataset.seq_name, 
                              maxlen=max([len(l) for l in dataset.seq_name]))
        ,'ntk': pad_sequences(dataset.seq_name_token, 
                              maxlen=max([len(l) for l in dataset.seq_name_token]))
        ,'nst': pad_sequences(dataset.seq_name_token_stem, 
                              maxlen=max([len(l) for l in dataset.seq_name_token_stem]))
        ,'item_desc': pad_sequences(dataset.seq_item_description, 
                              maxlen=max([len(l) for l in dataset.seq_item_description]))
        #,'dst': pad_sequences(dataset.seq_item_description_stem, 
        #                      maxlen=max([len(l) for l in dataset.seq_item_description_stem]))
        ,'brand': np.array(dataset.brand)
        ,'category': np.array(dataset.category)
        ,'category_name_split': pad_sequences(dataset.seq_category_name_split, 
                              maxlen=max([len(l) for l in dataset.seq_category_name_split]))
        ,'item_condition': np.array(dataset.item_condition_id)
        ,'num_vars': np.array(dataset[["shipping"]])
        ,'lost_feat': np.array(dataset["lost_features"].tolist())
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

def trn_generator(dn, dt, y, bsize):
    while True:
        max_step, batch_steps, sorted_ix, dt = reset_data(dt, bsize)
        for batch in batch_steps:
            from_ = batch*bsize
            to_   = min((batch+1)*bsize, max_step)
            ix_   = sorted_ix[from_:to_]
            Xbatch = dt.iloc[ix_]
            Xbatch = get_keras_data(Xbatch)
            Xbatch['dense_name'] = dn[ix_]
            ybatch = dt.target.iloc[ix_]
            yield Xbatch, ybatch

def val_generator(dn, dt, y, bsize):
    while 1:
        max_step, batch_steps, sorted_ix, dt = reset_data(dt, bsize)
        for batch in batch_steps:
            from_ = batch*bsize
            to_   = min((batch+1)*bsize, max_step)
            ix_   = sorted_ix[from_:to_]
            Xbatch = dt.iloc[ix_]
            Xbatch = get_keras_data(Xbatch)
            Xbatch['dense_name'] = dn[ix_]
            ybatch = dt.target.iloc[ix_]
            yield Xbatch, ybatch
            
def tst_generator(dn, dt, bsize):
    while 1:
        for batch in range(int(np.ceil(dt.shape[0]*1./bsize))):
        #for batch in range(dt.shape[0]/bsize+1):
            from_ = batch*bsize
            to_   = min((batch+1)*bsize, dt.shape[0])
            Xbatch = dt.iloc[from_:to_]
            Xbatch = get_keras_data(Xbatch)
            Xbatch['dense_name'] = dn[from_:to_]
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
    nst = Input(shape=[None], name="nst")
    #dst = Input(shape=[None], name="dst")
    item_desc = Input(shape=[None], name="item_desc")
    category_name_split = Input(shape=[None], name="category_name_split")
    brand = Input(shape=[1], name="brand")
    item_condition = Input(shape=[1], name="item_condition")
    num_vars = Input(shape=[1], name="num_vars")
    dense_name = Input(shape=[densetrn.shape[1]], name="dense_name")
    
    #Embeddings layers
    emb_size = 60
    emb_name                = Embedding(MAX_NAM, emb_size//2)(name) 
    emb_ntk                 = Embedding(MAX_NTK, emb_size//2)(ntk) 
    emb_nst                 = Embedding(MAX_NST, emb_size//2)(nst) 
    emb_item_desc           = Embedding(MAX_DSC, emb_size)(item_desc) 
    emb_category_name_split = Embedding(MAX_CAT, emb_size//3)(category_name_split) 
    emb_brand               = Embedding(MAX_BRAND, 16)(brand)
    emb_item_condition      = Embedding(MAX_CONDITION, 5)(item_condition)
    
    rnn_layer1 = GRU(16, recurrent_dropout=0.0) (emb_item_desc)
    rnn_layer2 = GRU(8, recurrent_dropout=0.0) (emb_category_name_split)
    rnn_layer3 = GRU(8, recurrent_dropout=0.0) (emb_name)
    rnn_layer4 = GRU(8, recurrent_dropout=0.0) (emb_ntk)
    rnn_layer5 = GRU(8, recurrent_dropout=0.0) (emb_nst)
    
    dense_l = Dropout(dr*2)(Dense(32,activation='relu') (dense_name))
    
    #main layer
    main_l = concatenate([
        Flatten() (emb_brand)
        , Flatten() (emb_item_condition)
        , rnn_layer1
        , rnn_layer2
        , rnn_layer3
        , rnn_layer4
        , rnn_layer5
        , dense_l
        , num_vars
    ])
    main_l = Dropout(dr)(Dense(256,activation='relu') (main_l))
    main_l = Dropout(dr)(Dense(64,activation='relu') (main_l))
    
    #output
    output = Dense(1,activation="linear") (main_l)
    
    #model
    model = Model([name, brand, ntk, item_desc, dense_name, nst
                   , category_name_split #,category
                   , item_condition, num_vars], output)
    optimizer = optimizers.Adam()
    model.compile(loss='mse', 
                  optimizer=optimizer)
    return model

print('[{}] Finished DEFINING MODEL...'.format(time.time() - start_time))

y_pred_epochs = []
yspred_epochs = []

def run_me():
    y_pred_epochsfn = []
    yspred_epochsfn = []
    epochs = 2
    batchSize = 512 * 4
    steps = (dtrain.shape[0]/batchSize+1)*epochs
    lr_init, lr_fin = 0.015, 0.011
    lr_decay  = (lr_init - lr_fin)/steps
    model = get_model()
    K.set_value(model.optimizer.lr, lr_init)
    K.set_value(model.optimizer.decay, lr_decay)
    model.fit_generator(
                        trn_generator(densetrn, dtrain, dtrain.target, batchSize)
                        , epochs=epochs
                        , max_queue_size=1
                        , steps_per_epoch = int(np.ceil(dtrain.shape[0]*1./batchSize))
                        , validation_data = val_generator(denseval, dvalid, dvalid.target, batchSize)
                        , validation_steps = int(np.ceil(dvalid.shape[0]*1./batchSize))
                        , verbose=2
                        )
    
    
    val_sorted_ix = np.array(map_sort(dvalid["seq_item_description"].tolist(), dvalid["seq_name_token"].tolist()))
    tst_sorted_ix = np.array(map_sort(test  ["seq_item_description"].tolist(), test  ["seq_name_token"].tolist()))
    for c, lr in enumerate([ 0.010, 0.010]):
        K.set_value(model.optimizer.lr, lr)
        model.fit_generator(
                            trn_generator(densetrn, dtrain, dtrain.target, batchSize)
                            , epochs=1#,epochs
                            , max_queue_size=1
                            , steps_per_epoch = int(np.ceil(dtrain.shape[0]*1./batchSize))
                            , validation_data = val_generator(denseval, dvalid, dvalid.target, batchSize)
                            , validation_steps = int(np.ceil(dvalid.shape[0]*1./batchSize))
                            , verbose=2
                            )
        y_pred_epochsfn.append(model.predict_generator(
                        tst_generator(denseval[val_sorted_ix], dvalid.iloc[val_sorted_ix], batchSize)
                        , steps = int(np.ceil(dvalid.shape[0]*1./batchSize))
                        , max_queue_size=1 
                        , verbose=2)[val_sorted_ix.argsort()])
        yspred_epochsfn.append(model.predict_generator(
                        tst_generator(densetst[tst_sorted_ix], test.iloc[tst_sorted_ix], batchSize)
                        , steps = int(np.ceil(test.shape[0]*1./batchSize))
                        , max_queue_size=1 
                        , verbose=2)[tst_sorted_ix.argsort()])
        print("Epoch %s rmsle %s"%(epochs+c+1, eval_model(dvalid.price.values, y_pred_epochsfn[-1])))
    return y_pred_epochsfn, yspred_epochsfn
    
for bag in range(2):
    l1, l2 = run_me()
    y_pred_epochs += l1
    yspred_epochs += l2

y_pred = sum(y_pred_epochs)/len(y_pred_epochs)
yspred = sum(yspred_epochs)/len(yspred_epochs)
print("Bagged nnet rmsle %s"%(eval_model(dvalid.price.values, y_pred)))
# Bagged Epoch 5 rmsle 0.427645675244
'''
Start the lightgbm
'''

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

#llcols = [("seq_category_name_split", MAX_CAT), ("seq_item_description", MAX_DSC), \
#          ("seq_name", MAX_NAM), ("seq_name_token", MAX_NTK)]
llcols = [("seq_category_name_split", MAX_CAT), ("seq_item_description", MAX_DSC), \
          ("seq_name_token", MAX_NTK)]
lcols = ["brand", "item_condition_id", "shipping", "category"]

spmatval = hstack([col2sparse(dvalid[c_].tolist(), max_col = max_val) for (c_, max_val) in llcols] + \
                  [col2sparse([[l] for l in dvalid[c_].tolist()], \
                               max_col = max(dtrain[c_].tolist())+1) for c_ in lcols]).tocsr().astype(np.float32)
spmattrn = hstack([col2sparse(dtrain[c_].tolist(), max_col = max_val) for (c_, max_val) in llcols] + \
                  [col2sparse([[l] for l in dtrain[c_].tolist()], \
                               max_col = max(dtrain[c_].tolist())+1) for c_ in lcols]).tocsr().astype(np.float32)
spmattst = hstack([col2sparse(test [c_].tolist(), max_col = max_val) for (c_, max_val) in llcols] + \
                  [col2sparse([[l] for l in test [c_].tolist()], \
                               max_col = max(dtrain[c_].tolist())+1) for c_ in lcols]).tocsr().astype(np.float32)
print(spmatval.shape)
print(spmattst.shape)
print(spmattrn.shape)

# Feature Engineering - Bayes Mean and count
n_folds = 2 
folds = np.array([random.randint(1,n_folds) for i in range(dtrain.shape[0])])

def bayesMean(dt_in, dt_out, t_col = "brand", y_col = "target"):
    mean_dict  = pd.groupby(dt_in[[t_col, y_col]], t_col).mean().to_dict()[y_col]
    ct_dict   = pd.groupby(dt_in[[t_col, y_col]], t_col).count().to_dict()[y_col]
    glbmean  = dt_in[y_col].values.mean()
    def bMeanSngl(vc, vm, glbmean = glbmean, prior = 5):
        return ((vc*vm)+(prior*glbmean))/(vc+prior)
    bmean_dict = dict((kc, bMeanSngl(vc, vm)) for ((kc, vc), (km, vm)) in \
                      zip(ct_dict.items(), mean_dict.items()))
    out = dt_out[t_col].apply(lambda x : bmean_dict.get(x, glbmean)).values
    return out

dtrain.head()
bcols = ["brand", "category"]
trn_bayes_mean = np.zeros((dtrain.shape[0], len(bcols)), dtype=float)
val_bayes_mean = np.zeros((dvalid.shape[0], len(bcols)), dtype=float)
tst_bayes_mean = np.zeros((test.shape[0], len(bcols)), dtype=float)

# Fill in out training set
for i in range(len(bcols)):
    for f in range(n_folds):
        idx_ = folds == 1+f
        trn_bayes_mean[~idx_, i] = bayesMean(dtrain[idx_], dtrain[~idx_], t_col = bcols[i])
# Now fill in valid and test set
for i in range(len(bcols)):
    val_bayes_mean[:, i] = bayesMean(dtrain, dvalid, t_col = bcols[i])
    tst_bayes_mean[:, i] = bayesMean(dtrain, test, t_col = bcols[i])
    

spmatval = hstack([spmatval, csr_matrix(spmatval.sum(axis=1)), csr_matrix(val_bayes_mean), csr_matrix(np.array(dvalid["lost_features"].tolist()))])
spmattrn = hstack([spmattrn, csr_matrix(spmattrn.sum(axis=1)), csr_matrix(trn_bayes_mean), csr_matrix(np.array(dtrain["lost_features"].tolist()))])
spmattst = hstack([spmattst, csr_matrix(spmattst.sum(axis=1)), csr_matrix(tst_bayes_mean), csr_matrix(np.array(test["lost_features"].tolist()))])


d_train = lgb.Dataset(spmattrn, label=dtrain.target)#, max_bin=1024)
d_valid = lgb.Dataset(spmatval, label=dvalid.target)#, max_bin=1024)
d_test  = lgb.Dataset(spmattst)#, max_bin=8192)
watchlist = [d_train, d_valid]

params = {
    'learning_rate': 0.75,
    'application': 'regression',
    'max_depth': 3,
    'num_leaves': 99,
    'verbosity': -1,
    'metric': 'RMSE',
    'nthread': 4,
    'feature_fraction':0.7,
    'max_bin' : 16,#1024
}
num_rounds = 5500

modellgb = lgb.train(params, train_set=d_train, num_boost_round=num_rounds, valid_sets=watchlist, \
early_stopping_rounds=500, verbose_eval=250) 
#[4000]  training's rmse: 0.426448       valid_1's rmse: 0.450838
#[7500]  training's rmse: 0.407931       valid_1's rmse: 0.445383
y_predlgb = modellgb.predict(spmatval)
y_predlgb = np.expand_dims(y_predlgb, 1)
yspredlgb = modellgb.predict(spmattst)
yspredlgb = np.expand_dims(yspredlgb, 1)

print("LGB trees rmsle %s"%( eval_model(dvalid.price.values, y_predlgb)))
# LGB trees rmsle 0.445382854056
'''
from sklearn.linear_model import Ridge
model = Ridge(solver="sag", fit_intercept=True, random_state=205, alpha=3)
model.fit(spmattrn, dtrain.target)
print('[{}] Finished to train ridge sag'.format(time.time() - start_time))
y_predsRval = model.predict(X=spmatval)
y_predsRtst = model.predict(X=spmattst)
print('[{}] Finished to predict ridge sag'.format(time.time() - start_time))
y_predsRval = np.expand_dims(y_predsRval, 1)
print("Ridge rmsle %s"%( eval_model(dvalid.price.values, y_predsRval)))
'''
y_predbag = 0.3*y_predlgb+0.7*y_pred 
yspredbag = 0.3*yspredlgb+0.7*yspred
print("Bagged rmsle %s"%(eval_model(dvalid.price.values, y_predbag)))
# Bagged rmsle 0.418875993307

'''
dvalid['pred'] = np.expm1(y_predbag)
ix_ = np.argsort(np.absolute(dvalid.target.values-y_predbag[:,0]))
dvalid[['brand_name', 'price', 'pred','name', 'name_token', 'item_description']].iloc[ \
        ix_[-1000:]].to_csv('../explore/topk_wrong_rows.csv')
dvalid[['brand_name', 'price', 'pred','name', 'name_token', 'item_description']].iloc[ \
        ix_[:1000]].to_csv('../explore/topk_right_rows.csv')
print("Bagged rmsle %s"%(eval_model(dvalid.price.values[74127:], y_predbag[74127:])))

train[train.item_description.str.contains('[rm]')].price.mean()
train.price.mean()
dvalid[[ 'price', 'pred']].iloc[np.argsort(np.absolute(dvalid.target.values-y_predbag[:,0]))]
'''

print('[{}] Finished FITTING MODEL...'.format(time.time() - start_time))

#CREATE PREDICTIONS
preds = np.expm1(yspredbag)
print('[{}] Finished predicting test set...'.format(time.time() - start_time))
submission = test[["test_id"]]
submission["price"] = preds
# submission.to_csv("./myBag_2604.csv", index=False)
submission.to_csv("../sub/myBag_2704.csv.gz", index=False)
#submission.to_csv("./myBag"+log_subdir+"_{:.6}.csv".format(v_rmsle), index=False)
print('[{}] Finished submission...'.format(time.time() - start_time))