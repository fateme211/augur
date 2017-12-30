import numpy as np
from pdb import set_trace
import os,re

def HI_model(process):
    '''
    estimate a tree and substitution model using titers.
    '''
    from base.titer_model import TreeModel, SubstitutionModel

    ## define the kwargs explicitly
    kwargs = process.config["titers"]
    # if "criterium" in process.config["titers"]:
    #     kwargs["criterium"] = process.config["titers"]["criterium"]

    ## TREE MODEL
    process.HI_tree = TreeModel(process.tree.tree, process.titers, **kwargs)
    process.HI_tree.prepare(**kwargs)
    process.HI_tree.train(**kwargs)
    # add tree attributes to the list of attributes that are saved in intermediate files
    for n in process.tree.tree.find_clades():
        n.attr['cTiter'] = n.cTiter
        n.attr['dTiter'] = n.dTiter
        # print("cumulative: {} delta: {}".format(n.cTiter, n.dTiter))
    process.config["auspice"]["color_options"]["cTiter"] = {
        "menuItem": "antigenic advance", "type": "continuous", "legendTitle": "Antigenic Advance", "key": "cTiter"
    }

    # SUBSTITUTION MODEL
    process.HI_subs = SubstitutionModel(process.tree.tree, process.titers, **kwargs)
    process.HI_subs.prepare(**kwargs)
    process.HI_subs.train(**kwargs)


def HI_export(process):
    from base.io_util import write_json
    prefix = os.path.join(process.config["output"]["auspice"], process.info["prefix"])
    if hasattr(process, 'HI_tree'):
        # export the raw titers
        hi_data = process.HI_tree.compile_titers()
        write_json(hi_data, prefix+'_titers.json')
        # export the tree model (avidities and potencies only)
        tree_model = {'potency':process.HI_tree.compile_potencies(),
                      'avidity':process.HI_tree.compile_virus_effects(),
                      'dTiter':{n.clade:n.dTiter for n in process.tree.tree.find_clades() if n.dTiter>1e-6}}
        write_json(tree_model, prefix+'_titer_tree_model.json')
    else:
        print('Tree model not yet trained')

    if hasattr(process, 'HI_subs'):
        # export the substitution model
        subs_model = {'potency':process.HI_subs.compile_potencies(),
                      'avidity':process.HI_subs.compile_virus_effects(),
                      'substitution':process.HI_subs.compile_substitution_effects()}
        write_json(subs_model, prefix+'_titer_subs_model.json')
    else:
        print('Substitution model not yet trained')


def get_total_peptide(node):
    '''
    the concatenation of signal peptide, HA1, HA1
    '''
    return np.fromstring(node.translations['SigPep']+node.translations['HA1']
                   + node.translations['HA2'], 'S1')


def seasonal_flu_scores(runner, tree):

    def glycosylation_count(aa):
        # need to restrict to surface residues.
        return len(re.findall('N[^P][ST][^P]', aa))

    root = tree.root
    root_total_aa_seq = get_total_peptide(root)
    for node in tree.find_clades():
        total_aa_seq = get_total_peptide(node)
        node.attr['glyc'] = glycosylation_count(total_aa_seq)

    for node in tree.get_terminals():
        node.tip_count=1.0
        if ('age' in node.attr) and type(node.attr['age']) in [str, unicode]:
            tmp_age = node.attr['age']
            if tmp_age[-1] in ['y', 'm']:
                node.attr['age'] = int(tmp_age[:-1])
                if tmp_age[-1]=='m':
                    node.attr['age']/=12.0
                elif node.attr['age']>120:
                    node.attr['age'] = 'unknown'
            else:
                node.attr['age'] = 'unknown'
        else:
            node.attr['age'] = 'unknown'


    for node in tree.get_nonterminals(order='postorder'):
        valid_ages = [c.attr['age'] for c in node if c.attr['age'] is not "unknown"]
        valid_tipcounts = [c.tip_count for c in node if c.attr['age'] is not "unknown"]
        if len(valid_ages):
            node.attr['age'] = np.sum([a*t for a,t in zip(valid_ages, valid_tipcounts)])/np.sum(valid_tipcounts)
            node.tip_count = np.sum(valid_tipcounts)
        else:
            node.attr['age'] = "unknown"

    for node in tree.get_terminals():
        node.tip_count=1.0
        if ('gender' in node.attr) and type(node.attr['gender']) in [str, unicode]:
            g = node.attr["gender"]
            node.attr["num_gender"] = -1 if g=='male' else (1 if g=='female' else 0)
        else:
            node.attr["num_gender"] = 0

    for node in tree.get_nonterminals(order='postorder'):
        node.tip_count = np.sum([c.tip_count for c in node])
        node.attr['num_gender'] = np.sum([c.attr['num_gender']*c.tip_count for c in node])/node.tip_count


    runner.config["auspice"]["color_options"]["glyc"] = {
        "menuItem": "potential glycosylation sites",
        "type": "continuous",
        "legendTitle": "Pot. glycosylation count",
        "key": "glyc"
    }
    runner.config["auspice"]["color_options"]["age"] = {
        "menuItem": "average host age in clade",
        "type": "continuous",
        "legendTitle": "Avg host age in clade",
        "key": "age"
    }
    runner.config["auspice"]["color_options"]["gender"] = {
        "menuItem": "average host gender in clade",
        "type": "continuous",
        "legendTitle": "Avg host gender in clade",
        "key": "num_gender"
    }


def H3N2_scores(runner, tree, epitope_mask_file, epitope_mask_version='wolf'):
    '''
    takes a H3N2 HA tree and assigns H3 specific characteristics to
    internal and external nodes
    '''
    def epitope_sites(aa):
        return aa[epitope_mask[:len(aa)]]

    def nonepitope_sites(aa):
        return aa[~epitope_mask[:len(aa)]]

    def receptor_binding_sites(aa):
        '''
        Receptor binding site mutations from Koel et al. 2014
        These are (145, 155, 156, 158, 159, 189, 193) in canonical HA numbering
        need to subtract one since python arrays start at 0
        '''
        sp = 16
        rbs = map(lambda x:x+sp-1, [145, 155, 156, 158, 159, 189, 193])
        return np.array([aa[pos] for pos in rbs])


    def epitope_distance(aaA, aaB):
        """Return distance of sequences aaA and aaB by comparing epitope sites"""
        epA = epitope_sites(aaA)
        epB = epitope_sites(aaB)
        distance = np.sum(epA!=epB)
        return distance

    def nonepitope_distance(aaA, aaB):
        """Return distance of sequences aaA and aaB by comparing non-epitope sites"""
        neA = nonepitope_sites(aaA)
        neB = nonepitope_sites(aaB)
        distance = np.sum(neA!=neB)
        return distance

    def receptor_binding_distance(aaA, aaB):
        """Return distance of sequences aaA and aaB by comparing receptor binding sites"""
        neA = receptor_binding_sites(aaA)
        neB = receptor_binding_sites(aaB)
        distance = np.sum(neA!=neB)
        return distance

    epitope_map = {}
    with open(epitope_mask_file) as f:
        for line in f:
            (key, value) = line.strip().split()
            epitope_map[key] = value
    if epitope_mask_version in epitope_map:
        epitope_mask = np.fromstring(epitope_map[epitope_mask_version], 'S1')=='1'
    root = tree.root
    root_total_aa_seq = get_total_peptide(root)
    for node in tree.find_clades():
        total_aa_seq = get_total_peptide(node)
        node.attr['ep'] = epitope_distance(total_aa_seq, root_total_aa_seq)
        node.attr['ne'] = nonepitope_distance(total_aa_seq, root_total_aa_seq)
        node.attr['rb'] = receptor_binding_distance(total_aa_seq, root_total_aa_seq)


    runner.config["auspice"]["color_options"]["ep"] = {
        "menuItem": "epitope mutations",
        "type": "continuous",
        "legendTitle": "Epitope mutations",
        "key": "ep"
    }
    runner.config["auspice"]["color_options"]["ne"] = {
        "menuItem": "non-epitope mutations",
        "type": "continuous",
        "legendTitle": "Non-epitope mutations",
        "key": "ne"
    }
    runner.config["auspice"]["color_options"]["rb"] = {
        "menuItem": "receptor binding mutations",
        "type": "continuous",
        "legendTitle": "Receptor binding mutations",
        "key": "rb"
    }
