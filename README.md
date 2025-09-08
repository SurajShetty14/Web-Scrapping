## Flexible Web Scraper (AccioMatrix-ready)

Scrape AccioMatrix assessment reports (and similar pages) and export to Excel/CSV/JSON. Works on Windows with Chrome.

### 1) Setup (Windows PowerShell)

```powershell
cd "C:\Gisul\Scrapping Accoimatrix"
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2) Run a single URL

```powershell
python flexible_scraper.py --url "https://web.acciomatrix.com/assessment-user-report/705d6358-8618-4a67-a2e1-c563da68e318" --fields fields.sample.yaml --config config.sample.yaml --out assessment_reports --out-dir outputs
```

### 3) Run multiple URLs from file

Create a `urls.txt` with one URL per line, then run:

```powershell
python flexible_scraper.py --url-file urls.txt --fields fields.sample.yaml --config config.sample.yaml --out assessment_reports --out-dir outputs
```

### 4) Customizing fields

- Edit `fields.sample.yaml` to add or change fields. Each field supports:
  - css_selectors
  - xpath (Selenium only)
  - text_patterns (regex with one capturing group)
  - attributes (selector + attribute)
  - transform (regex | strip_chars | convert_to_number)

### 5) Outputs

The script saves timestamped files next to the script:

- By default inside `outputs/` (configurable via `--out-dir` or `output_dir` in config)
- Excel: `assessment_reports_YYYYMMDD_HHMMSS.xlsx`
- CSV: `assessment_reports_YYYYMMDD_HHMMSS.csv`
- JSON: `assessment_reports_YYYYMMDD_HHMMSS.json`

### 6) Notes

- Chrome and ChromeDriver are handled automatically via `webdriver-manager`. If it fails, ensure Chrome is installed and try again.
- If the site loads content dynamically, keep Selenium enabled; Requests-only may miss data.
- Use `config.sample.yaml` to toggle headless mode, save HTML, or add API endpoints.

(.venv) PS C:\Gisul\Scrapping Accoimatrix> python flexible_scraper.py --url "https://web.acciomatrix.com/assessment-user-report/705d6358-8618-4a67-a2e1-c563da68e318" --fields fields.sample.yaml --config config.sample.yaml --out assessment_reports

