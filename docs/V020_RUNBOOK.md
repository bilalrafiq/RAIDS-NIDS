# RAIDS-NIDS v0.20 Windows runbook

## Folder preparation

Keep the complete v0.19 folder as an archive:

```text
C:\Users\ASUS\raids-nids-v019-failed-archive
```

Extract the v0.1.10 package so the new project root is:

```text
C:\Users\ASUS\raids-nids
```

Copy only these existing evidence files from the archive into the new project:

```text
data\raw\NF-UNSW-NB15-v3.csv
data\derived\v019_unsw_temporal.npz
data\derived\v019_unsw_temporal.json
data\derived\v019_unsw_events\NF-UNSW-NB15-v3-v019-suite-manifest.json
```

Do not copy the old source code, configurations, notebooks, or result
directories into the new project.

## Install and verify

Open Anaconda Prompt:

```bat
conda activate raids-nids
cd /d C:\Users\ASUS\raids-nids
python -m pip install -e ".[dev]"
python -c "import raids_nids, river; print(raids_nids.__version__); print(raids_nids.__file__); print(river.__version__)"
```

Expected versions:

```text
0.1.10
0.25.0
```

Run the tests:

```bat
python -m pytest -q
```

Then start:

```bat
python -m jupyter notebook RAIDS_NIDS_v020_Amended_External_Guard_Starter.ipynb
```

Use the kernel connected to the `raids-nids` Conda environment.

## First execution boundary

Run through event construction and dataset audits only. Keep:

```python
RUN_SEED11 = False
RUN_FULL_MATRICES = False
```

Send the printed amended suite and episode-review table before changing either
flag. The review must confirm:

- DoS remains failed;
- Exploits and Reconnaissance construct as expected;
- every hash matches;
- the held-out family is absent from its source;
- every warm-up family is source-known;
- any additional novel target families are recorded.

Only then should seed 11 be activated.
