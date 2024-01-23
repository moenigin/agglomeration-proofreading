import argparse
import json
import os
import re

from brainmaps_api_fcn.equivalence_requests import EquivalenceRequests
from graph_from_bigquery.graph_from_bigquery import BigQueryAgglomerationGraph
from agglomeration_proofreading.neuron_proofreader import NeuronProofreading
from agglomeration_proofreading.API_interface import GraphTools
from agglomeration_proofreading.config_fcn import determine_args
from agglomeration_proofreading.ap_utils import keys_to_int

# Todo wrap around Gooey, make this optional when run from command line
def run_proofreading(args):
    """Sets arguments from parser and starts proofreading tool

    Args:
        args (argparse.ArgumentParser.parse_args())
    """
    pattern = re.compile(r'\d{6}_\d{6}\_agglomerationReview.json')
    try:
        latest_file = max(filter(pattern.search, os.listdir(args.dir_path)))
        full_fn = os.path.join(args.dir_path, latest_file)
        with open(full_fn, 'rb') as f:
            review_data = json.load(f)
        review_data['neuron_graph'] = keys_to_int(review_data[
                                                      'neuron_graph'])
        for dct in review_data['action_history']:
            key = next(iter(dct.keys()))
            val = dct[key]
            if key == 'split':
                dct[key] = [val[0], keys_to_int(val[1])]
            else:
                if isinstance(val, dict):
                    dct[key] = keys_to_int(val)
                else:
                    print('The data in ', full_fn, 'has unexpected format '
                          'and could not be loaded')

    except ValueError:  # thrown by max if no file with pattern found
        review_data = None
    except FileNotFoundError:
        print("The path for data storage is not found. Please enter a valid "
              "path in the proofreading.ini. Alternatively, the path can be set"
              " by calling the proofreading tool with the flag -dir_path "
              "<path_to_directory>")
        return

    if not os.path.exists(args.service_account):
        print('Please enter valid path to service account file via the command '
              'line or to the proofreading.ini')
        raise FileNotFoundError

    brainmaps_api_fcn = EquivalenceRequests(volume_id=args.base_volume,
                                            change_stack_id=args.change_stack_id,
                                            service_account_secrets=args.service_account)

    graph_tool = GraphTools(api_fcn=brainmaps_api_fcn)
    base_path = args.data_src + args.base_volume
    raw_path = args.data_src + args.raw_data

    with NeuronProofreading(dir_path=args.dir_path,
                            data=review_data,
                            graph_tool=graph_tool,
                            base_vol=base_path,
                            raw_data=raw_path,
                            timer_interval=args.save_int,
                            remove_token=args.remove_token) as aobr:
        aobr.exit_event.wait()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()

    ap.add_argument("-config_path",
                    type=str,
                    help="path to config file")

    ap.add_argument("-dir_path",
                    type=str,
                    help="path to directory for saving proofreading data")

    ap.add_argument('-service_account',
                    type=str,
                    help='path to the service account file for API'
                         ' authentication')

    ap.add_argument('-base_volume',
                    type=str,
                    help='base segmentation volume id in form of '
                         '"projectId:datasetId:volumeId"')

    ap.add_argument('-raw_data',
                    type=str,
                    help='image data volume path')

    ap.add_argument('-data_src',
                    type=str,
                    help='data source')

    ap.add_argument('-change_stack_id',
                    type=str,
                    help='id of the change stack storing the agglomeration '
                         'graph')

    ap.add_argument('-save_int',
                    type=int,
                    help='interval in which automatic data saving is triggered')

    ap.add_argument('-remove_token',
                    help='flag that decides whether to delete the token created'
                         ' by authenticating to neuroglancer upon exit of the '
                         'program')

    ap.set_defaults(func=run_proofreading)

    ap_args = ap.parse_args()

    args = determine_args(ap_args)

    ap_args.func(args)
