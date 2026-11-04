# Run the experimental baseline on Kaggle

These steps run a small **raw-label experiment**. The meaning of labels 0 and 1 is not verified, so results are not vulnerability-detection claims. Before uploading derived source code, review the dataset's applicable license, attribution obligations and rights in the underlying code; those rights have not been verified. Keep the dataset and notebook private.

## Files to use

Locate these files on your PC:

- `E:\PatchWars Ai\data\processed\train.csv`
- `E:\PatchWars Ai\data\processed\validation.csv`
- `E:\PatchWars Ai\ml\train_baseline.py`
- `E:\PatchWars Ai\kaggle\baseline.ipynb` (import this into the notebook, not into the dataset)

Do not upload `test.csv` for this first experiment. Do not upload `archive.zip`. The notebook expects the first three files together in the same attached dataset folder.

## Create and attach a private dataset

1. Sign in to Kaggle and open [Datasets](https://www.kaggle.com/datasets). Select **New Dataset**.
2. Select the three files `train.csv`, `validation.csv`, and `train_baseline.py` from the locations above. Upload them together as files at the dataset root. Give the dataset a name.
3. Check that its sharing or visibility is **Private**, then create it. Kaggle's [dataset documentation](https://www.kaggle.com/docs/datasets) explains visibility and sharing. Private does not itself establish permission to upload the data.
4. From the dataset page, use **Code** / **Create a notebook**, or create a new notebook and use the Input panel's **Add Input** to attach your private dataset. The [notebook guide](https://www.kaggle.com/docs/notebooks) describes adding datasets. Keep the notebook private as well.

## Import and run

1. In the notebook editor, use **File > Import Notebook** and choose the local `kaggle/baseline.ipynb`. If the editor labels differ, look for its notebook import/upload option. Reattach the private dataset via **Add Input** if needed.
2. Run the cells from top to bottom using each cell's run button or Shift+Enter. The first cell finds the attached files, and the second displays the installed scikit-learn version. If scikit-learn is absent, the notebook stops with an error; it does not install packages.
3. The third code cell runs `train_baseline.py` with `--experimental-raw-labels`, `--train-limit 2000`, `--max-features 5000`, `--max-chars 10000`, and `--metrics-output /kaggle/working/metrics.json`. It fits only the first 2,000 training rows and evaluates the validation split. The fixed seed is 42. The sample is ordered and may not be representative.
4. The final cell displays the JSON metrics. Find `metrics.json` under the notebook's working/output files. Download it using the file's download control. If it is not visible in the editor, save a notebook version and check its Output tab. Share the downloaded `metrics.json` here for review; do not share the source CSVs.

The script refuses to overwrite an existing metrics file. Before rerunning, download or move the old file, or restart with a clean working directory. No model file is saved by this notebook. No metrics exist until the experiment succeeds.
