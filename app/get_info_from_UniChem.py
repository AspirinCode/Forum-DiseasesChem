import rdflib
import requests
import io
import re
from rdflib.namespace import XSD, DCTERMS, OWL
import os
import json
import itertools
from Database_ressource_version import Database_ressource_version

def get_mapping(ressource_1, ressource_2):
    """
    This function is used to send a request to the mapping WebService of UniChem from ressources ids.
    """
    request_base = "https://www.ebi.ac.uk/unichem/rest/mapping/" + ressource_1 + "/" + ressource_2
    try:
        # On lance la requête. Si le statut HTTP de la requête raise est > 200, cela déclenche une exception, on ajoute l'offset_concerné dans la table
        r = requests.get(request_base)
        r.raise_for_status()
    except requests.exceptions.HTTPError as fail_request:
        print("There was an error during the request : " + fail_request + "\n")
    lines = str.splitlines(r.text)
    content = json.loads(lines[0])
    ids_ressource_1 = r = [mapping[ressource_1] for mapping in content]
    ids_ressource_2 = r = [mapping[ressource_2] for mapping in content]
    return(ids_ressource_1, ids_ressource_2)

def get_graph_ids_set(path_to_graph, graph_original_uri_prefix, ressource_uris):
    """
    This function allow to parse an input SMBL RDF graph and get all the actual ids present in the graph ONLY for ressources that may have several uris.
    - path_to_graph: a path to the .ttl file of the SMBL graph
    - graph_original_uri_prefix: a dict with key as ressource name and value as the original root uri (so without the id) used in the graph. Exemple for Chebi : http://purl.obolibrary.org/obo/CHEBI_
      Note that keys in the dict must be the same as in the ressource_uris dict.
    - ressource_uris: a dict containing all the possible ressources uris that may be used. It will be used to choose for which ressource, ids should be extracted to compute intra-uris equivalence.
      Note that keys in the dict must be the same as in the graph_original_uri_prefix dict.
    """
    intra_ids_dict = {key: set() for key in ressources_ids.keys() if len(ressource_uris[key]) > 1 }
    g = rdflib.Graph()
    g.parse(path_to_graph, format = 'turtle')
    query = g.query(
        """
        select distinct ?ref
        where {
            ?species a SBMLrdf:Species .
            ?species bqbiol:is ?ref .
            }
        """)
    uri_list = [uriRef[0].toPython() for uriRef in query]
    for uri in uri_list:
        for key in intra_ids_dict.keys():
            split_uri = uri.split(graph_original_uri_prefix[key])
            if len(split_uri) > 1:
                # Sachant que l'on a fai la requête avec distinct, pas besoin de union, on peut directement add, il n'y aura pas de duplicats
                intra_ids_dict[key].add(split_uri[1])
    return(intra_ids_dict)

def create_graph(path_to_graph, ressources_ids, ressource_uris, namespaces, path_out, version):
    """
    This function is used to create a graph or uri equivalences between different input ressource. Equivalence information are fetch for the WebService of UniChem. 
    Between ressource a skos:closeMatch relation is implemented (to avoid propaging false information)
    Between differents uris of the same ressource (called intra-uris) a skos:exactMatch relation is implemented
    - ressources_ids: a dict containing ressource name as key and ressource id in the UniChem database as values
    - ressource_uris: a dict containing all the possible ressources uris that may be used. It will be used to choose for which ressource, ids should be extracted to compute intra-uris equivalence.
      Note that keys in the dict must be the same as in the graph_original_uri_prefix dict.
    - namespaces: a dict of namespaces
    - path_out: a path to out files
    """
    ressource_version = Database_ressource_version(ressource = "ressources_id_mapping", version = version)
    # On ne prépare se dictionnaire que pour les ressource avec plus d'une URI :
    intra_ids_dict = get_graph_ids_set(path_to_graph, graph_original_uri_prefix, ressource_uris)
    path_out = path_out + ressource_version.version + "/"
    if not os.path.exists(path_out):
        os.makedirs(path_out)
    cbn_resource = itertools.combinations(ressources_ids.keys(), 2)
    for ressource_pair in cbn_resource:
        r1 = ressource_pair[0]
        r2 = ressource_pair[1]
        g_name = (r1 + "_" + r2)
        print("Treating : " + r1 + " - " + r2 + " ...")
        ressource_version.append_data_graph(file = g_name + ".trig", namespace_list  = ["skos"], namespace_dict = namespaces)
        ids_r1, ids_r2 = get_mapping(ressources_ids[r1], ressources_ids[r2])
        print("Data fetch from UniChem Ok")
        n_ids = len(ids_r1)
        for id_index in range(n_ids):
            #  On écrit les équivalence inter-ressource seulement pour une URI de chaque ressource, le liens avec les autres se fera par le biais des équivalence intra-ressource
            all_uris = [rdflib.URIRef(ressource_uris[r1][0] + ids_r1[id_index])] + [rdflib.URIRef(ressource_uris[r2][0] + ids_r2[id_index])]
            for current_uri, next_uri in zip(all_uris, all_uris[1:]):
                ressource_version.data_graph_dict[g_name].add((current_uri, namespaces["skos"]['closeMatch'], next_uri))
        # On écrit le graph :
        ressource_version.data_graph_dict[g_name].serialize(destination = path_out + g_name + ".trig", format='trig')
        # Si il y a plusieurs URI pour la ressource, il faut préparer les identifiants pour les correspondances intra-ressource
        if len(ressource_uris[r1]) > 1:
            intra_ids_dict[r1] = intra_ids_dict[r1].union(ids_r1)
        if len(ressource_uris[r2]) > 1:
            intra_ids_dict[r2] = intra_ids_dict[r2].union(ids_r2)
    # On écrit les équivalence intra-ressource
    for r_name in intra_ids_dict.keys():
        g_name = r_name + "_intra"
        ressource_version.append_data_graph(file = (g_name + ".trig"), namespace_list  = ["skos"], namespace_dict = namespaces)
        intra_ids = list(intra_ids_dict[r_name])
        for id in intra_ids:
            intra_uris = [rdflib.URIRef(prefix + id) for prefix in ressource_uris[r_name]]
            for current_uri, next_uri in zip(intra_uris, intra_uris[1:]):
                ressource_version.data_graph_dict[g_name].add((current_uri, namespaces["skos"]['exactMatch'], next_uri))
        ressource_version.data_graph_dict[g_name].serialize(destination = path_out + g_name + ".trig", format='trig')
    # On annote le graph :
    ressource_version.add_version_namespaces(["void"], namespaces)
    ressource_version.add_version_attribute(DCTERMS["description"], rdflib.Literal("Ids correspondances between differents ressources in SBML"))
    ressource_version.add_version_attribute(DCTERMS["title"], rdflib.Literal("Ids correspondances"))
    ressource_version.add_version_attribute(namespaces["void"]["triples"], rdflib.Literal(sum([len(g) for g in ressource_version.data_graph_dict.values()]) , datatype=XSD.long ))
    ressource_version.add_version_attribute(namespaces["void"]["distinctSubjects"], rdflib.Literal( len(set([s for g in ressource_version.data_graph_dict.values() for s in g.subjects()])), datatype=XSD.long ))
    ressource_version.version_graph.serialize(destination=path_out + "ressource_info_ids_correspondance" + ressource_version.version + ".ttl", format = 'turtle')




namespaces = {
    "cito": rdflib.Namespace("http://purl.org/spar/cito/"),
    "compound": rdflib.Namespace("http://rdf.ncbi.nlm.nih.gov/pubchem/compound/"),
    "reference": rdflib.Namespace("http://rdf.ncbi.nlm.nih.gov/pubchem/reference/"),
    "endpoint":	rdflib.Namespace("http://rdf.ncbi.nlm.nih.gov/pubchem/endpoint/"),
    "obo": rdflib.Namespace("http://purl.obolibrary.org/obo/"),
    "dcterms": rdflib.Namespace("http://purl.org/dc/terms/"),
    "fabio": rdflib.Namespace("http://purl.org/spar/fabio/"),
    "mesh": rdflib.Namespace("http://id.nlm.nih.gov/mesh/"),
    "void": rdflib.Namespace("http://rdfs.org/ns/void#"),
    "skos": rdflib.Namespace("http://www.w3.org/2004/02/skos/core#"),
    "owl": OWL
}

ressources_ids = {
    "chebi": '7',
    "pubchem": '22',
    "kegg": '6',
    "hmdb": '18',
    "lipidmaps": '33'            
}

ressource_uris = {
    "chebi": ["http://identifiers.org/chebi/CHEBI:", "http://purl.obolibrary.org/obo/CHEBI_", "https://www.ebi.ac.uk/chebi/searchId.do?chebiId=CHEBI:"],
    "pubchem": ["http://identifiers.org/pubchem.compound/", "http://rdf.ncbi.nlm.nih.gov/pubchem/compound/CID"],
    "kegg": ["http://identifiers.org/kegg.compound/", "https://www.kegg.jp/entry/"],
    "hmdb": ["http://identifiers.org/hmdb/"],
    "lipidmaps": ["http://identifiers.org/lipidmaps/"] 
}

graph_original_uri_prefix = {
    "chebi": "http://identifiers.org/chebi/CHEBI:",
    "pubchem": "http://identifiers.org/pubchem.compound/",
    "kegg": "http://identifiers.org/kegg.compound/",
    "hmdb": "http://identifiers.org/hmdb/",
    "lipidmaps": "http://identifiers.org/lipidmaps/"
}
path_to_graph = "data/HumanGEM/HumanGEM.ttl"
 
create_graph(path_to_graph, ressources_ids, ressource_uris, namespaces, "data/UniChem/", None)