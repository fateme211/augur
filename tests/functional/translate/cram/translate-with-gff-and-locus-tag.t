Setup

  $ export AUGUR="${AUGUR:-$TESTDIR/../../../../bin/augur}"
  $ export DATA="$TESTDIR/../data"
  $ export SCRIPTS="$TESTDIR/../../../../scripts"

This is an identical test setup as `translate-with-gff-and-gene.t` but using locus_tag instead of gene in the GFF

  $ cat >genemap.gff <<~~
  > ##gff-version 3
  > ##sequence-region PF13/251013_18 1 10769
  > PF13/251013_18	GenBank	gene	91	456	.	+	.	locus_tag="CA"
  > PF13/251013_18	GenBank	gene	457	735	.	+	.	locus_tag="PRO"
  > ~~

  $ ${AUGUR} translate \
  >   --tree "${DATA}/zika/tree.nwk" \
  >   --ancestral-sequences "${DATA}/zika/nt_muts.json" \
  >   --reference-sequence genemap.gff \
  >   --output-node-data aa_muts.json
  Read in 3 features from reference sequence file
  Validating schema of '.+/nt_muts.json'... (re)
  amino acid mutations written to .* (re)

  $ python3 "${SCRIPTS}/diff_jsons.py" \
  >  --exclude-regex-paths "['seqid']" -- \
  >  "${DATA}/zika/aa_muts_gff.json" \
  >  aa_muts.json
  {}
