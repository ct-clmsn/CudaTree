import numpy as np
from cuda_random_decisiontree_small import RandomDecisionTreeSmall
from util import timer, get_best_dtype, dtype_to_ctype, mk_kernel, mk_tex_kernel
from pycuda import gpuarray

class RandomForestClassifier(object):
  COMPT_THREADS_PER_BLOCK = 64 
  RESHUFFLE_THREADS_PER_BLOCK = 64 
  
  def __compact_labels(self, target):
    def check_is_compacted(x):
      return x.size == int(np.max(x)) + 1 and int(np.min(x)) == 0
    def convert_to_dict(x):
      d = {}
      for i, val in enumerate(x):
        d[val] = i
      return d

    self.compt_table = np.unique(target)
    self.compt_table.sort()        
    if not check_is_compacted(self.compt_table):
      trans_table = convert_to_dict(self.compt_table)
      for i, val in enumerate(target):
        target[i] = trans_table[val]

  def fit(self, samples, target, n_trees = 10, min_samples_leaf = None, max_features = None, max_depth = None):
    assert isinstance(samples, np.ndarray)
    assert isinstance(target, np.ndarray)
    assert samples.size / samples[0].size == target.size

    target = target.copy()
    self.__compact_labels(target)
    self.n_labels = self.compt_table.size 

    self.dtype_indices = get_best_dtype(target.size)
    self.dtype_counts = self.dtype_indices
    self.dtype_labels = get_best_dtype(self.n_labels)
    self.dtype_samples = samples.dtype
   
    samples = np.require(np.transpose(samples), requirements = 'C')
    target = np.require(np.transpose(target), dtype = self.dtype_labels, requirements = 'C') 
    self.n_features = samples.shape[0]
    self.n_samples = target.size
    
    samples_gpu = gpuarray.to_gpu(samples)
    labels_gpu = gpuarray.to_gpu(target) 
    
    sorted_indices = np.empty((self.n_features, target.size), dtype = self.dtype_indices)
    
    with timer("argsort"):
      for i,f in enumerate(samples):
        sort_idx = np.argsort(f)
        sorted_indices[i] = sort_idx  
 
    self.forest = [RandomDecisionTreeSmall(samples_gpu, labels_gpu, sorted_indices, self.compt_table, 
      self.dtype_labels,self.dtype_samples, self.dtype_indices, self.dtype_counts,
      self.n_features, self.n_samples, self.n_labels, self.COMPT_THREADS_PER_BLOCK,
      self.RESHUFFLE_THREADS_PER_BLOCK, max_features, max_depth, min_samples_leaf) for i in xrange(n_trees)]   
   
    for i, tree in enumerate(self.forest):
      with timer("Tree %s" % (i,)):
        tree.fit(samples, target)

  def predict(self, x):
    res = []
    for tree in self.forest:
      res.append(tree.gpu_predict(x))
    res = np.array(res)
    return np.array([np.argmax(np.bincount(res[:,i])) for i in xrange(res.shape[1])]) 

