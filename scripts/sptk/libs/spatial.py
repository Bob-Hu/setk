#!/usr/bin/env python
# wujian@2018
"""
Some functions for spatial feature computation
"""
import numpy as np


def linear_tdoa_grid(dist,
                     speed=340,
                     num_bins=513,
                     samp_doa=True,
                     sample_frequency=16000,
                     num_doa=181,
                     max_doa=np.pi):
    """
    Construct transform matrix T:
        T_{ij} = 2 pi omega_i tau_j
        where i = 0..F j == 0..D-1
    """
    dist = np.abs(dist)  # make sure >= 0
    if samp_doa:
        # sample doa from 0 to pi
        doa_samp = np.linspace(0, max_doa, num_doa)
        tdoa = np.cos(doa_samp) * dist / speed
    else:
        # sample tdoa
        max_tdoa = dist / speed
        tdoa = np.linspace(max_tdoa, -max_tdoa, num_doa)
    omega = np.linspace(0, sample_frequency / 2, num_bins)
    return np.exp(np.outer(2j * np.pi * omega, tdoa))


def gcc_phat(si, sj, dij, normalize=True, apply_floor=True, **kwargs):
    """
    SRP-PHAT algorithm
    Arguments:
        si, sj: shape as T x F
        dij: distance between microphone i and j
        kwargs: kwargs for linear_tdoa_grid
    Return:
        shape as T x D
    """
    coherence = si * sj.conj() / (np.abs(si) * np.abs(sj))
    # transform: F x D
    transform = linear_tdoa_grid(dij, **kwargs)
    spectrum = np.real(coherence @ transform)
    if normalize:
        spectrum = spectrum / np.max(np.abs(spectrum))
    if apply_floor:
        spectrum = np.maximum(spectrum, 0)
    return spectrum


def srp_phat(S, d, normalize=True, apply_floor=True, **kwargs):
    """
    SRP-PHAT algorithm
    Arguments:
        S: multi-channel STFT, shape as N x T x F
        d: topology for linear microphone arrays
        kwargs: kwargs for linear_tdoa_grid
    Return:
        shape as T x D
    """
    if type(d) is not list:
        raise ValueError("Now only support linear arrays(in python list type)")
    N = S.shape[0]
    if N != len(d):
        raise ValueError(
            "{:d} microphones available, while get {:d}-channel STFT".format(
                len(d), N))
    if S.ndim == 2:
        raise ValueError("Only one-channel STFT available")
    gcc = gcc_phat(S[0], S[1], d[1] - d[0], **kwargs)
    if N == 2:
        return gcc
    srp = np.zeros_like(gcc)
    for i in range(N - 1):
        for j in range(i, N - 1):
            srp += gcc_phat(S[i], S[j], d[j] - d[i], normalize, apply_floor,
                            **kwargs)
    return srp * 2 / (N * (N - 1))


def msc(spectrogram, context=1, normalize=True):
    """
    Compute MSC(Magnitude Squared Coherence)
    Arguments:
        spectrogram: shape as N x T x F
    Reference:
        Wang Z Q, Wang D L. On Spatial Features for Supervised Speech Separation 
                            and its Application to Beamforming and Robust ASR
                            [C]//2018 IEEE International Conference on Acoustics, 
                            Speech and Signal Processing (ICASSP). IEEE, 2018: 5709-5713.
    """
    N, T, F = spectrogram.shape
    # C x N x T x F
    Y = np.zeros([(context * 2 + 1), N, T, F], dtype=np.complex)
    for t in range(T):
        for i, c in enumerate(range(-context, context + 1)):
            s = min(max(t + c, 0), T - 1)
            Y[i, :, t, :] = spectrogram[:, s, :]
    # N x N x T x F
    numerator = np.einsum("ab...,bc...->ac...", np.swapaxes(Y, 0, 1),
                          np.conj(Y)) / (context * 2 + 1)
    # N x T x F
    dig = np.abs(np.diagonal(numerator, axis1=0, axis2=1))
    dig = np.transpose(dig, [2, 0, 1])
    # N x N x T x F
    denumerator = np.sqrt(np.einsum("a...,b...->ab...", dig, dig))
    icc = np.abs(numerator / denumerator)
    # T x F
    coh = np.sum(np.diagonal(icc, axis1=0, axis2=1))
    coh += np.sum(np.sum(icc, axis=0), axis=0)
    # in [0, 1] ?
    coh = coh / (N * (N - 1))
    if normalize:
        coh = coh / np.max(np.abs(coh))
    return coh


def ipd(si, sj, sin=False):
    """
    Compute cosIPD/sinIPD spatial features
    Arguments:
        si, sj: shape as T x F
    Return:
        cosIPD: shape as T x F if sin=False
        [cosIPD, sinIPD]: shape as T x 2F if sin=True
    """
    ipd_mat = np.angle(si) - np.angle(sj)
    cos_ipd = np.cos(ipd_mat)
    if not sin:
        return cos_ipd
    sin_ipd = np.sin(ipd_mat)
    return np.concatenate((cos_ipd, sin_ipd), axis=1)
