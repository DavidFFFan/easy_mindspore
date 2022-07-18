import mindspore
from mindspore import Tensor
import mindspore.ops as ops
from .custom import *
from mindspore.ops._primitive_cache import _get_cache_prim
inf = float('inf')

def _check_dtype(d1, d2):
    if mindspore.float32 in (d1, d2):
        return mindspore.float32
    if d1 == d2:
        return d1
    raise ValueError('dtype is not supported.')

def dot(a, b):
    res_dtype = _check_dtype(a.dtype, b.dtype)
    ndim_a, ndim_b = a.ndim, b.ndim
    if ndim_a == 0 or ndim_b == 0:
        return ops.tensor_mul(a, b)
    if ndim_a > 0 and ndim_b >= 2:
        perm = ops.make_range(ndim_b)
        perm = perm[:-2] + (perm[-1],) + (perm[-2],)
        b = ops.transpose(b, perm)

    if a.shape[-1] != b.shape[-1]:
        raise ValueError('shapes are not aligned')
    a_aligned = a.reshape(-1, a.shape[-1]).astype(mindspore.float32)
    b_aligned = b.reshape(-1, b.shape[-1]).astype(mindspore.float32)

    res = ops.matmul(a_aligned, b_aligned.T)
    res = res.reshape(a.shape[:-1] + b.shape[:-1])

    return res.astype(res_dtype)

def sqrt(x):
    return ops.sqrt(x.astype(mindspore.float32))

def reciprocal(x):
    if isinstance(x, Tensor):
        reciprocal = _get_cache_prim(ops.Reciprocal)()
        return reciprocal(x)
    return 1/x

# grad operations
def get_grads():
    pass

def bmm(x, y, transpose_x=False, transpose_y=False):
    return _get_cache_prim(ops.BatchMatMul)(transpose_x, transpose_y)(x, y)

def masked_fill_(inputs:Tensor, mask:Tensor, value:float):
    return ops.masked_fill(inputs, mask, value)

def norm(x, ord=None, axis=None, keepdims=False):
    # Immediately handle some default, simple, fast, and common cases.
    if axis is None:
        ndim = x.ndim
        if ((ord is None) or
            (ord in ('f', 'fro') and ndim == 2) or
            (ord == 2 and ndim == 1)):

            x = x.ravel()
            sqnorm = dot(x, x)
            ret = sqrt(sqnorm)
            if keepdims:
                ret = ret.reshape(ndim*[1])
            return ret

    # Normalize the `axis` argument to a tuple.
    nd = x.ndim
    if axis is None:
        axis = tuple(range(nd))
    elif not isinstance(axis, tuple):
        try:
            axis = int(axis)
        except Exception as e:
            raise TypeError("'axis' must be None, an integer or a tuple of integers") from e
        axis = (axis,)

    if len(axis) == 1:
        if ord == inf:
            return ops.abs(x).max(axis=axis, keepdims=keepdims)
        elif ord == -inf:
            return ops.abs(x).min(axis=axis, keepdims=keepdims)
        elif ord == 0:
            # Zero norm
            return (x != 0).astype(x.dtype).sum(axis=axis, keepdims=keepdims)
        elif ord == 1:
            # special case for speedup
            reduce_sum = _get_cache_prim(ops.ReduceSum)(keepdims)
            return ops.reduce_sum(ops.abs(x), axis=axis)
        elif ord is None or ord == 2:
            # special case for speedup
            conj = _get_cache_prim(ops.Conj)()
            s = conj(x) * x
            reduce_sum = _get_cache_prim(ops.ReduceSum)(keepdims)
            return sqrt(reduce_sum(s, axis=axis))
        # None of the str-type keywords for ord ('fro', 'nuc')
        # are valid for vectors
        elif isinstance(ord, str):
            raise ValueError(f"Invalid norm order '{ord}' for vectors")
        else:
            absx = ops.abs(x)
            absx **= ord
            reduce_sum = _get_cache_prim(ops.ReduceSum)(keepdims)
            ret = reduce_sum(absx, axis=axis)
            ret **= reciprocal(ord)
            if ops.isnan(ret):
                return ops.zeros_like(ret)
            return ret
    elif len(axis) == 2:
        row_axis, col_axis = axis
        row_axis = normalize_axis_index(row_axis, nd)
        col_axis = normalize_axis_index(col_axis, nd)
        if row_axis == col_axis:
            raise ValueError('Duplicate axes given.')
        if ord == 2:
            ret =  _multi_svd_norm(x, row_axis, col_axis, 'amax')
        elif ord == -2:
            ret = _multi_svd_norm(x, row_axis, col_axis, 'amin')
        elif ord == 1:
            if col_axis > row_axis:
                col_axis -= 1
            ret = ops.reduce_sum(abs(x), axis=row_axis).max(axis=col_axis)
        elif ord == inf:
            if row_axis > col_axis:
                row_axis -= 1
            ret = ops.reduce_sum(abs(x), axis=col_axis).max(axis=row_axis)
        elif ord == -1:
            if col_axis > row_axis:
                col_axis -= 1
            ret = ops.reduce_sum(abs(x), axis=row_axis).min(axis=col_axis)
        elif ord == -inf:
            if row_axis > col_axis:
                row_axis -= 1
            ret = ops.reduce_sum(abs(x), axis=col_axis).min(axis=row_axis)
        elif ord in [None, 'fro', 'f']:
            conj = _get_cache_prim(ops.Conj)()
            ret = sqrt(ops.reduce_sum((conj(x) * x), axis=axis))
        elif ord == 'nuc':
            ret = _multi_svd_norm(x, row_axis, col_axis, sum)
        else:
            raise ValueError("Invalid norm order for matrices.")
        if keepdims:
            ret_shape = list(x.shape)
            ret_shape[axis[0]] = 1
            ret_shape[axis[1]] = 1
            ret = ret.reshape(ret_shape)
        return ret
    else:
        raise ValueError("Improper number of dimensions to norm.")

def _multi_svd_norm(x, row_axis, col_axis, op):
    y = moveaxis(x.astype(mindspore.float32), (row_axis, col_axis), (-2, -1))
    if op == 'amax':
        result = ops.svd(y, compute_uv=False).max(axis=-1)
    elif op == 'amin':
        result = ops.svd(y, compute_uv=False).min(axis=-1)
    return result

def normalize_axis_index(axis, ndim):
    if axis >= 0 and axis < ndim:
        return axis
    elif axis < 0 and axis >= -ndim:
        return ndim + axis
    else:
        raise ValueError('axis is out of range.')

def moveaxis(x, source, destination):
    perm = [i for i in range(x.ndim)]
    for s, d in zip(source, destination):
        tmp = perm[s]
        perm[s] = perm[d]
        perm[d] = tmp
    perm = tuple(perm)
    return ops.transpose(x, perm)