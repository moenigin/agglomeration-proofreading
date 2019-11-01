from os.path import abspath, dirname, join
from configparser import ConfigParser

_DEFAULT_KEYS = ['dir_path', 'service_account', 'data_src', 'raw_data',
                 'base_volume', 'change_stack_id', 'save_int']
_DEFAULT_VALS = [r'',
                r'\\argon\moennila\BrainmapsAPI\fmi-aglomeration-proofreading-466fc0396c6a.json',
                'brainmaps://',
                '487208920048:adultob:full',
                '487208920048:adultob:seg_v2_9nm_484558417fb_18nm_fb_107004781_otfa',
                'rsg18-9_minover_cbs_glia_nila_20190409',
                '300'
                 ]

_DEFAULT_DIR = dirname(dirname(abspath(__file__)))
_DEFAULT_FN = 'proofreading.ini'


class _Arguments:
    def __init__(self):
        for arg in _DEFAULT_KEYS:
            setattr(self, arg, None)


def write_config(**kwargs):
    """writes config file for proofreading.

    Uses DEFAULT_KEYS and DEFAULT_VALS, if no arguments are given. Accepts
    following optional arguments:

    config_path (str) : path to which the config file should be written
                        (default =  parent directory of config_fcn.py)
    dir_path (str) : path to directory to which the proofreading data should be
                    written
    service_account (str) : path to the service account json fro API access
    data_src (str) : data source for the segmentation data
    base_vol (str) : volume id of the segmentation base volume
    change_stack_id (str) : id of the agglomeration volume
    save_int (int or str): interval between autosaving of the proofreading data
                            in seconds
    """
    config_path = _DEFAULT_DIR
    config = ConfigParser()
    config['DEFAULTS'] = {}
    for idx, key in enumerate(_DEFAULT_KEYS):
        config['DEFAULTS'][key] = _DEFAULT_VALS[idx]

    for key, val in kwargs.items():
        if key in _DEFAULT_KEYS:
            config['DEFAULTS'][key] = str(val)
        if key == 'config_path':
            config_path = val

    config_fn = join(config_path, _DEFAULT_FN)

    with open(config_fn, 'w') as f:
        config.write(f)


def determine_args(ap_args):
    """parses config and overwrites default, if given as command line
    arguments

    Args:
        ap_args (NameSpace object from argparse.ArgumentParser.parse-args)

    Returns:
        args (Arguments object) : object that stores arguments for the
                                    proofreading function as attributes
    """
    if not ap_args.config_path:
        config_fn = join(_DEFAULT_DIR, _DEFAULT_FN)
    else:
        config_fn = join(ap_args.config_path, _DEFAULT_FN)
    config = ConfigParser()
    config.read(config_fn)

    args = _Arguments()
    for key in _DEFAULT_KEYS:
        if getattr(ap_args, key):
            setattr(args, key, getattr(ap_args, key))
        else:
            setattr(args, key, config['DEFAULTS'][key])

    args.save_int = int(args.save_int)

    return args
