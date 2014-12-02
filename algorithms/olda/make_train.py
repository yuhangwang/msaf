#!/usr/bin/env python

import argparse
import numpy as np
import glob
import os
import sys
import time

from joblib import Parallel, delayed
import cPickle as pickle

import msaf
import librosa

from segmenter import features


def align_segmentation(filename, beat_times,  song):
    '''Load a ground-truth segmentation, and align times to the nearest detected beats

    Arguments:
        filename -- str
        beat_times -- array
        song -- path to the audio file

    Returns:
        segment_beats -- array
            beat-aligned segment boundaries

        segment_times -- array
            true segment times

        segment_labels -- array
            list of segment labels
    '''

    context_dict = {
        "Isophonics": "function",
        "SALAMI": "small_case",
        "Cerulean": "large_case",
        "Epiphyte": "function"
    }

    #segment_times, segment_labels = mir_eval.io.load_jams_range(filename,
                    #"sections", annotator=0, converter=None,
                    #label_prefix='__', context="function")
    segment_times, segment_labels = msaf.io.read_references(song)
    segment_times = np.asarray(segment_times)

    # Map to intervals
    segment_intervals = msaf.utils.times_to_intervals(segment_times)

    # Map beats to intervals
    beat_intervals = np.asarray(zip(beat_times[:-1], beat_times[1:]))

    # Map beats to segments
    #segment_times = np.concatenate((np.asarray(segment_times).flatten()[::2],
                                    #[segment_times[-1, 1]]))
    #res = []
    #for segment_interval in segment_intervals:
        #res.append(segment_interval[0])
    #res.append(segment_intervals[-1, -1])
    #segment_intervals = np.asarray(res)

    beat_segment_ids = librosa.util.match_intervals(beat_intervals, segment_intervals)

    segment_beats = []
    segment_times_out = []
    segment_labels_out = []

    #print segment_times, beat_segment_ids, len(beat_times), len(beat_segment_ids)
    for i in range(segment_times.shape[0]):
        hits = np.argwhere(beat_segment_ids == i)
        if len(hits) > 0 and i < len(segment_intervals) and \
                i < len(segment_labels):
            segment_beats.extend(hits[0])
            segment_times_out.append(segment_intervals[i, :])
            segment_labels_out.append(segment_labels[i])

    # Pull out the segment start times
    segment_beats = list(segment_beats)
    #segment_times_out = np.asarray(segment_times_out)[:, 0].squeeze().reshape((-1, 1))

    #if segment_times_out.ndim == 0:
    #    segment_times_out = segment_times_out[np.newaxis]
    segment_times_out = segment_times

    return segment_beats, segment_times_out, segment_labels_out


def get_annotation(song, rootpath):
    return '%s/annotations/%s.jams' % (rootpath, os.path.basename(song)[:-4])


def import_data(song, rootpath, output_path, annot_beats):
    msaf.utils.ensure_dir(output_path)
    msaf.utils.ensure_dir(os.path.join(output_path, "features"))
    data_file = '%s/features/%s_annotbeatsE%d.pickle' % \
        (output_path, os.path.splitext(os.path.basename(song))[0], annot_beats)

    if os.path.exists(data_file):
        with open(data_file, 'r') as f:
            Data = pickle.load(f)
            print song, 'cached!'
    else:
        #try:
        X, B, dur = features(song, annot_beats)

        #plt.imshow(X, interpolation="nearest", aspect="auto"); plt.show()

        if X is None:
            return X

        Y, T, L = align_segmentation(get_annotation(song, rootpath), B, song)

        Data = {'features': X,
                'beats': B,
                'filename': song,
                'segment_times': T,
                'segment_labels': L,
                'segments': Y}
        print song, 'processed!'

        with open(data_file, 'w') as f:
            pickle.dump(Data, f)
        #except Exception as e:
        #    print song, 'failed!'
        #    print e
        #    Data = None

    return Data


def make_dataset(n=None, n_jobs=1, rootpath='', output_path='',
                 annot_beats=False):

    # We don't care about prefix, only those which have annot beats
    audio_files = glob.glob('%s/audio/Epiphyte_*.[wm][ap][v3]' % (rootpath))

    if n is None:
        n = np.min([len(audio_files), 400])

    data = Parallel(n_jobs=n_jobs)(delayed(import_data)(song,
            rootpath, output_path, annot_beats)
            for song in audio_files[:n])

    X, Y, B, T, F, L = [], [], [], [], [], []
    for d in data:
        if d is None:
            continue
        if d['features'].shape[0] != 94:
            continue
        X.append(d['features'])
        Y.append(d['segments'])
        B.append(d['beats'])
        T.append(d['segment_times'])
        F.append(d['filename'])
        L.append(d['segment_labels'])

    return X, Y, B, T, F, L


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=
        "Extracts a set of features from the Segmentation dataset or a given "
        "audio file and saves them into the 'features' folder of the dataset",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("ds_path",
                        action="store",
                        help="Input dataset dir or audio file")
    parser.add_argument("output_path",
                        action="store",
                        help="Output dir to store the features")
    parser.add_argument("-n",
                        action="store",
                        dest="n",
                        type=int,
                        help="Number of files to process (None for all)",
                        default=None)
    parser.add_argument("-j",
                        action="store",
                        dest="n_jobs",
                        type=int,
                        help="Number of jobs (threads)",
                        default=8)
    parser.add_argument("-b",
                        action="store_true",
                        dest="annot_beats",
                        help="Use annotated beats",
                        default=False)
    args = parser.parse_args()
    start_time = time.time()
    salami_path = sys.argv[1]
    output_path = sys.argv[2]
    X, Y, B, T, F, L = make_dataset(n=args.n,
                            n_jobs=args.n_jobs,
                            rootpath=args.ds_path,
                            output_path=args.output_path,
                            annot_beats=args.annot_beats)

    if args.annot_beats:
        out_path = '%s/AnnotBeats_data.pickle' % (output_path)
    else:
        out_path = '%s/EstBeats_data.pickle' % (output_path)
    with open(out_path, 'w') as f:
        pickle.dump((X, Y, B, T, F, L), f)