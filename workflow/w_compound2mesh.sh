#!/bin/bash

BASEDIR=$(dirname $0)
LOGSDIR=./logs-app

mkdir -p $LOGSDIR

# -v: la version de l'analyse CID/CHEBI/CHEMONT to mesh
# -m: le chemin vers le fichier de configuration de l'analyse compound2mesh (eg. app/metab2mesh/config/CID_MESH_Thesaurus/test/config.ini)
# -t: le chemin vers le fichier de configuration du processus association-to-triples (eg. app/Analyzes/Enrichment_to_graph/config/CID_MESH/2020-07-07/config.ini)
# -u: le nom de la ressource créée par l'analyse (eg. CID_MESH ou CHEBI_MESH)
# -d: le chemin vers le répertoire où écrire les données (eg. ./data)
# -s: le chemin vers le répertoire de partage de Virtuoso où écrire les triplets (eg/ ./docker-virtuoso/share)



# Init logs
echo "" > $LOGSDIR/post_processes.log

while getopts v:m:t:u:d:s: flag
	do
	    case "${flag}" in
	        v) VERSION=${OPTARG};;
            m) CONFIG_COMPOUND2MESH=${OPTARG};;
            t) CONFIG_COMPOUND2MESH_TRIPLES=${OPTARG};;
			u) RESSOURCE_NAME=${OPTARG};;
			d) DATA=${OPTARG};;
			s) RESOURCES_DIR=${OPTARG};;
	    esac
	done

# Compute compound 2 mesh

# Compute fisher exact tests
echo " - compute compound2mesh"

OUT_M="${DATA}/metab2mesh/${RESSOURCE_NAME}/${VERSION}/"

python3 app/metab2mesh/metab2mesh_requesting_virtuoso.py --config=$CONFIG_COMPOUND2MESH --out=$OUT_M 2>&1 | tee -a $LOGSDIR/post_processes.log

echo " - compute fisher exact tests"

IN_F="${DATA}/metab2mesh/${RESSOURCE_NAME}/${VERSION}/results/metab2mesh.csv"
OUT_F="${DATA}/metab2mesh/${RESSOURCE_NAME}/${VERSION}/r_fisher.csv"

Rscript app/metab2mesh/post-processes/compute_fisher_exact_test_V2.R --file=$IN_F --chunksize=100000 --parallel=5 --p_out=$OUT_F 2>&1 | tee -a $LOGSDIR/post_processes.log

# Compute post-processes (eg. q.value)
echo " - Compute benjamini and Holchberg procedure"

IN_Q=$OUT_F
OUT_Q="${DATA}/metab2mesh/${RESSOURCE_NAME}/${VERSION}/r_fisher_q.csv"

Rscript app/metab2mesh/post-processes/post_process_metab2mesh.R --p_metab2mesh=$IN_Q --p_out=$OUT_Q 2>&1 | tee -a $LOGSDIR/post_processes.log

# Compute weakness test
echo " - Compute weakness tests"

IN_W=$OUT_Q
OUT_W="${DATA}/metab2mesh/${RESSOURCE_NAME}/${VERSION}/r_fisher_q_w.csv"
Rscript app/metab2mesh/post-processes/weakness/weakness_test.R --file=$IN_W --threshold=1e-6 --alphaCI=0.05 --chunksize=100000 --parallel=5 --p_out=$OUT_W 2>&1 | tee -a $LOGSDIR/post_processes.log

# Upload step - Skip for now
#TODO
FTP="ftp://data/anayse/version"

# Create triples

echo " - Convert significant relations to triples"

IN_T=$OUT_W

python3 app/Analyzes/Enrichment_to_graph/convert_association_table_to_triples.py --config=$CONFIG_COMPOUND2MESH_TRIPLES --input=$IN_T --uri=$FTP --version=$VERSION --out=$RESOURCES_DIR 2>&1 | tee -a $LOGSDIR/post_processes.log