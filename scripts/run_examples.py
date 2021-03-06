import argparse
import numpy
import warnings
import logging
import gzip
import random
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 
from vivisect.servers import flush, clear
warnings.simplefilter(action='ignore', category=FutureWarning)


def onehot(i, r):
    retval = [0] * r
    retval[i] = 1.0
    return retval

           
if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", dest="host", default="0.0.0.0", help="Host name")
    parser.add_argument("--port", dest="port", default=8082, type=int, help="Port number")
    parser.add_argument("--frontend_host", dest="frontend_host", default="0.0.0.0", help="Host name")
    parser.add_argument("--frontend_port", dest="frontend_port", default=8080, type=int, help="Port number")
    parser.add_argument("--epochs", dest="epochs", default=10, type=int, help="Maximum training epochs")
    parser.add_argument("--hidden_size", dest="hidden_size", default=50, type=int, help="Hidden size for MLPs/LSTMs")
    parser.add_argument("--input", dest="input", default="data/lid.txt.gz", help="")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    
    # generate some synthetic data from a mixture model
    n_mlp_feats = 20
    n_mlp_labels = 3
    train_class_probs = numpy.random.dirichlet([1.0 for i in range(n_mlp_labels)])
    dev_class_probs = numpy.random.dirichlet([1.0 for i in range(n_mlp_labels)])
    test_class_probs = numpy.random.dirichlet([1.0 for i in range(n_mlp_labels)])
    obs_probs = numpy.random.dirichlet([1.0 for i in range(n_mlp_feats)], size=n_mlp_labels)
    y_train = numpy.asarray([random.randint(0, 2) for _ in range(1000)], dtype=numpy.int64)
    y_dev = numpy.asarray([random.randint(0, 2) for _ in range(100)], dtype=numpy.int64)
    y_test = numpy.asarray([random.randint(0, 2) for _ in range(100)], dtype=numpy.int64)
    x_train = numpy.asfarray([numpy.random.multinomial(10, obs_probs[c, :], size=1) for c in y_train]).squeeze()
    x_dev = numpy.asfarray([numpy.random.multinomial(10, obs_probs[c, :], size=1) for c in y_dev]).squeeze()
    x_test = numpy.asfarray([numpy.random.multinomial(10, obs_probs[c, :], size=1) for c in y_test]).squeeze()
    

    # read some data for an RNN model
    instances = []
    char_lookup = {"<S>" : 0, "</S>" : 1}
    label_lookup = {}
    with gzip.open(args.input, "rt") as ifd:
        for line in ifd:
            label, text = line.strip().split("\t")
            instances.append((label_lookup.setdefault(label, len(label_lookup)), [0] + [char_lookup.setdefault(c, len(char_lookup)) for c in text] + [1]))
    random.shuffle(instances)
    instances = instances[0:100]
    train_instances = instances[0:int(.8 * len(instances))]
    y_rnn_train = numpy.asarray([l for l, _ in train_instances])
    lengths_rnn_train = numpy.asarray([len(cs) for _, cs in train_instances])
    x_rnn_train = numpy.asarray([[onehot(x, len(char_lookup)) for x in xs] + ([[0] * len(char_lookup)] * (max(lengths_rnn_train) - len(xs))) for _, xs in train_instances])
    dev_instances = instances[int(.8 * len(instances)) : int(.9 * len(instances))]    
    y_rnn_dev = numpy.asarray([l for l, _ in dev_instances])
    lengths_rnn_dev = numpy.asarray([len(cs) for _, cs in dev_instances])
    x_rnn_dev = numpy.asarray([[onehot(x, len(char_lookup)) for x in xs] + ([[0] * len(char_lookup)] * (max(lengths_rnn_dev) - len(xs))) for _, xs in dev_instances])
    test_instances = instances[int(.9 * len(instances)):]
    y_rnn_test = numpy.asarray([l for l, _ in test_instances])
    lengths_rnn_test = numpy.asarray([len(cs) for _, cs in test_instances])
    x_rnn_test = numpy.asarray([[onehot(x, len(char_lookup)) for x in xs] + ([[0] * len(char_lookup)] * (max(lengths_rnn_test) - len(xs))) for _, xs in test_instances])
    n_rnn_labels = len(label_lookup)
    n_rnn_feats = len(char_lookup)


    def monitor(layer):
        return True

    def perform(model, op, inputs, outputs):
        return model._vivisect["mode"] == "train"

    clear(args.host, args.port)
    clear(args.frontend_host, args.frontend_port)

    
    logging.info("Testing with Tensorflow 'Session'")
    import tensorflow
    from vivisect.tensorflow import probe, train, mlp, rnn

    logging.info("MLP model")    
    model = mlp(n_mlp_feats, n_mlp_labels, args.hidden_size)
    model._vivisect = {"iteration" : 0, "model_name" : "Tensorflow MLP Model", "framework" : "tensorflow"}
    assert(isinstance(model, tensorflow.Session))
    probe(model, args.host, args.port, lambda m : m.name in ["layer1/bias", "layer2/bias"], perform)
    train(model, x_train, y_train, x_dev, y_dev, x_test, y_test, args.epochs)
    
    logging.info("RNN model")
    model = rnn(n_rnn_feats, n_rnn_labels, args.hidden_size)
    model._vivisect = {"iteration" : 0, "model_name" : "Tensorflow RNNe Model", "framework" : "tensorflow"}
    assert(isinstance(model, tensorflow.Session))
    probe(model, args.host, args.port)
    train(model, (x_rnn_train, lengths_rnn_train), y_rnn_train, (x_rnn_dev, lengths_rnn_dev), y_rnn_dev, (x_rnn_test, lengths_rnn_test), y_rnn_test, args.epochs)
    

    logging.info("Testing with PyTorch 'Module'")
    import torch    
    from vivisect.pytorch import probe, train, mlp, rnn

    logging.info("PyTorch MLP model")    
    model = mlp(n_mlp_feats, n_mlp_labels, args.hidden_size)
    model._vivisect = {"iteration" : 0, "model_name" : "PyTorch MLP Model", "framework" : "pytorch"}
    assert(isinstance(model, torch.nn.Module))
    probe(model, args.host, args.port, monitor, perform)
    train(model, x_train, y_train, x_dev, y_dev, x_test, y_test, args.epochs)
    
    logging.info("PyTorch RNN model")
    model = rnn(n_rnn_feats, n_rnn_labels, args.hidden_size)
    model._vivisect = {"iteration" : 0, "model_name" : "PyTorch RNN Model", "framework" : "pytorch"}
    assert(isinstance(model, torch.nn.Module))
    probe(model, args.host, args.port, monitor, perform)
    train(model, (x_rnn_train, lengths_rnn_train), y_rnn_train, (x_rnn_dev, lengths_rnn_dev), y_rnn_dev, (x_rnn_test, lengths_rnn_test), y_rnn_test, args.epochs)

    
    logging.info("Testing with MXNet 'Block'")
    import mxnet
    from vivisect.mxnet import probe, train, mlp, rnn
    from mxnet.gluon import Block, HybridBlock, SymbolBlock, Trainer
    
    logging.info("MXNet MLP model")
    model = mlp(n_mlp_feats, n_mlp_labels, args.hidden_size)
    model._vivisect = {"iteration" : 0, "model_name" : "MXNet MLP Model", "framework" : "mxnet"}    
    assert(isinstance(model, mxnet.gluon.Block))
    probe(model, args.host, args.port)
    train(model, x_train, y_train, x_dev, y_dev, x_test, y_test, args.epochs)
    
    logging.info("MXNet RNN model")
    model = rnn(n_rnn_feats, n_rnn_labels, args.hidden_size)
    model._vivisect = {"iteration" : 0, "model_name" : "MXNet RNN Model", "framework" : "mxnet"}    
    assert(isinstance(model, mxnet.gluon.Block))
    probe(model, args.host, args.port, monitor, perform)
    train(model, x_rnn_train, y_rnn_train, x_rnn_dev, y_rnn_dev, x_rnn_test, y_rnn_test, args.epochs)
    
    flush(args.host, args.port)
