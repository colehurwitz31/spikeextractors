from spikeinterface import InputExtractor
from spikeinterface import OutputExtractor

import numpy as np
from os.path import join
import h5py
import ctypes


class BiocamInputExtractor(InputExtractor):
    def __init__(self, *, dataset_directory, recording_files):
        InputExtractor.__init__(self)
        self._dataset_directory = dataset_directory
        self._recording_files = recording_files
        if type(recording_files) == list:
            if len(recording_files) != 1:
                raise NotImplementedError(
                    "Reading multiple files not yet implemented.")
            ifile = join(dataset_directory, recording_files[0])
        else:
            ifile = join(dataset_directory, recording_files)
        self._rf, self._nFrames, self._samplingRate, self._nRecCh, self._chIndices, self._file_format, self._signalInv, self._positions, self._read_function = openBiocamFile(
            ifile)

    def getNumChannels(self):
        return self._nRecCh

    def getNumFrames(self):
        return self._nFrames

    def getSamplingFrequency(self):
        return self._samplingRate

    def getRawTraces(self, start_frame=None, end_frame=None, channel_ids=None):
        if start_frame is None:
            start_frame = 0
        if end_frame is None:
            end_frame = self.getNumFrames()
        if channel_ids is None:
            channel_ids = range(self.getNumChannels())
        data = self._read_function(
            self._rf, start_frame, end_frame, self.getNumChannels())
        return data.reshape((end_frame - start_frame,
                             self.getNumChannels())).T[channel_ids]

    def getChannelInfo(self, channel_id):
        return dict(
            location=self._positions[channel_id]
        )


def openBiocamFile(filename):
    """Open a Biocam hdf5 file, read and return the recording info, pick te correct method to access raw data, and return this to the caller."""
    rf = h5py.File(filename, 'r')
    # Read recording variables
    recVars = rf.require_group('3BRecInfo/3BRecVars/')
    # bitDepth = recVars['BitDepth'].value[0]
    # maxV = recVars['MaxVolt'].value[0]
    # minV = recVars['MinVolt'].value[0]
    nFrames = recVars['NRecFrames'].value[0]
    samplingRate = recVars['SamplingRate'].value[0]
    signalInv = recVars['SignalInversion'].value[0]

    # Read chip variables
    chipVars = rf.require_group('3BRecInfo/3BMeaChip/')
    nCols = chipVars['NCols'].value[0]

    # Get the actual number of channels used in the recording
    file_format = rf['3BData'].attrs.get('Version')
    if file_format == 100:
        nRecCh = len(rf['3BData/Raw'][0])
        # raise Warning('This may go wrong!')
    elif file_format == 101:
        nRecCh = int(1. * rf['3BData/Raw'].shape[0] / nFrames)
    else:
        raise Exception('Unknown data file format.')

    print('# 3Brain data format:', file_format, 'signal inversion', signalInv)
    print('#       signal range: ', recVars['MinVolt'].value[0], '- ',
          recVars['MaxVolt'].value[0])
    # Compute indices
    rawIndices = rf['3BRecInfo/3BMeaStreams/Raw/Chs'].value

    # Name channels ([0..4095] for fullarray files)
    chIndices = [(x - 1) + (y - 1) * nCols for (y, x) in rawIndices]
    # chIndices = [(x-1) + (y-1)*nCols for (x,y) in rawIndices]
    # Swap X and Y (old format)

    # determine correct function to read data
    print("# Signal inversion looks like " + str(signalInv) + ", guessing the "
          "right method for data access.\n# If your results "
          "look strange, signal polarity is wrong.")
    if file_format == 100:
        if signalInv is -1:
            read_function = readHDF5t_100
        else:
            read_function = readHDF5t_100_i
    else:
        if signalInv is not -1:
            read_function = readHDF5t_101
        else:
            read_function = readHDF5t_101_i

    return (rf, nFrames, samplingRate, nRecCh, chIndices, file_format, signalInv, rawIndices, read_function)


def readHDF5(rf, t0, t1):
    """In order to use the algorithms designed for the old format, the input data must be inverted."""
    return 4095 - rf['3BData/Raw'][t0:t1].flatten().astype(ctypes.c_short)


def readHDF5t_100(rf, t0, t1, nch):
    """Transposed version for the interpolation method."""
    if t0 <= t1:
        d = 2048 - rf['3BData/Raw'][t0:t1].flatten('C').astype(ctypes.c_short)
        d[np.where(np.abs(d) > 1500)[0]] = 0
        return d
    else:  # Reversed read
        raise Exception('Reading backwards? Not sure about this.')
        return 2048 - rf['3BData/Raw'][t1:t0].flatten(
            'F').astype(ctypes.c_short)


def readHDF5t_100_i(rf, t0, t1, nch):
    ''' Transposed version for the interpolation method. '''
    if t0 <= t1:
        d = rf['3BData/Raw'][t0:t1].flatten('C').astype(ctypes.c_short) - 2048
        d[np.where(np.abs(d) > 1500)[0]] = 0
        return d
    else:  # Reversed read
        raise Exception('Reading backwards? Not sure about this.')
        return rf['3BData/Raw'][t1:t0].flatten(
            'F').astype(ctypes.c_short) - 2048


def readHDF5t_101(rf, t0, t1, nch):
    ''' Transposed version for the interpolation method. '''
    if t0 <= t1:
        d = rf['3BData/Raw'][nch * t0:nch * t1].reshape(
            (-1, nch), order='C').flatten('C').astype(ctypes.c_short) - 2048
        d[np.abs(d) > 1500] = 0
        return d
    else:  # Reversed read
        raise Exception('Reading backwards? Not sure about this.')
        d = rf['3BData/Raw'][nch * t1:nch * t0].reshape(
            (-1, nch), order='C').flatten('C').astype(ctypes.c_short) - 2048
        d[np.where(np.abs(d) > 1500)[0]] = 0
        return d


def readHDF5t_101_i(rf, t0, t1, nch):
    ''' Transposed version for the interpolation method. '''
    if t0 <= t1:
        d = 2048 - rf['3BData/Raw'][nch * t0:nch * t1].reshape(
            (-1, nch), order='C').flatten('C').astype(ctypes.c_short)
        d[np.where(np.abs(d) > 1500)[0]] = 0
        return d
    else:  # Reversed read
        raise Exception('Reading backwards? Not sure about this.')
        d = 2048 - rf['3BData/Raw'][nch * t1:nch * t0].reshape(
            (-1, nch), order='C').flatten('C').astype(ctypes.c_short)
        d[np.where(np.abs(d) > 1500)[0]] = 0
        return d
