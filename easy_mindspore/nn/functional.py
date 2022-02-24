import mindspore.ops as ops

def softmax(input, axis=-1):
    return ops.Softmax(axis)(input)

def log_softmax(input, axis=-1):
    return ops.LogSoftmax(axis)(input)

def kl_div(input, target, reduction='none', log_target=False):
    if log_target:
        kl_div = ops.exp(target) * (target - input)
    else:
        kl_div = target * (ops.log(target) - input)
    if reduction == 'sum':
        return kl_div.sum()
    if reduction == 'mean':
        return kl_div.mean()
    return kl_div

def cross_entropy(input, target, weight=None, ignore_index=-100, reduction='mean', label_smoothing=0.0):
    return nll_loss(log_softmax(input, 1), target, weight, ignore_index, reduction, label_smoothing)

def nll_loss(input, target, weight=None, ignore_index=None, reduction='mean', label_smoothing=0.0):
    ndim = input.ndim
    if ndim == 2:
        ret = _nll_loss(input, target, -1, weight, ignore_index, reduction)
    elif input.ndim == 4:
        ret = _nll_loss(input, target, 1, weight, ignore_index, reduction)
    else:
        # ndim == 3 or ndim > 4
        n = input.shape[0]
        c = input.shape[1]
        out_size = (n,) + input.shape[2:]
        input = input.view(n, c, 1, -1)
        target = target.view(n, 1, -1)
        if reduction != 'none':
            ret = _nll_loss(input, target, 1, weight, ignore_index, reduction)
        else:
            ret = _nll_loss(input, target, 1, weight, ignore_index)
            ret = ret.view(out_size)
    return ret

def _nll_loss(input, target, target_dim=-1, weight=None, ignore_index=None, reduction='none', label_smoothing=0.0):
    if target.ndim == input.ndim - 1:
        target = target.expand_dims(target_dim)
    nll_loss = -ops.gather_d(input, target_dim, target)
    smooth_loss = -input.sum(axis=target_dim, keepdims=True)
    if weight is not None:
        loss_weights = ops.gather(weight, target, 0)
        nll_loss = nll_loss * loss_weights
    else:
        loss_weights = ops.ones_like(nll_loss)
    if ignore_index is not None:
        non_pad_mask = ops.equal(target, ignore_index)
        nll_loss = nll_loss.masked_fill(non_pad_mask, 0.)
        loss_weights = loss_weights.masked_fill(non_pad_mask, 0.)
        smooth_loss = smooth_loss.masked_fill(non_pad_mask, 0.)
    else:
        nll_loss = nll_loss.squeeze(target_dim)
        smooth_loss = smooth_loss.squeeze(target_dim)

    if reduction == 'sum':
        nll_loss = nll_loss.sum()
    if reduction == 'mean':
        nll_loss = nll_loss.sum() / loss_weights.sum()

    eps_i = label_smoothing / input.shape[target_dim]
    loss = (1. - label_smoothing) * nll_loss + eps_i * smooth_loss
    return loss

def binary_cross_entropy(input, target, weight=None, reduction='mean'):
    pass

def binary_cross_entropy_with_logits(input, target, weight=None, reduction='mean', pos_weight=None):
    max_val = ops.maximum(-input, 0)

    if pos_weight is not None:
        log_weight = ((pos_weight - 1) * target) + 1
        loss = (1 - target) * input
        loss_1 = ops.log(ops.exp(-max_val) + ops.exp(-input - max_val)) + max_val
        loss += log_weight * loss_1
    else:
        loss = (1 - target) * input
        loss += max_val
        loss += ops.log(ops.exp(-max_val) + ops.exp(-input - max_val))
 
    if weight is not None:
        output = loss * weight
    else:
        output = loss

    if reduction == "mean":
        return ops.reduce_mean(output)
    elif reduction == "sum":
        return ops.reduce_sum(output)
    else:
        return output
