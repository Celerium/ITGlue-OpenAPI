# IT Glue OpenAPI

This repository generates an unofficial OpenAPI specification from the public [IT Glue developer documentation](https://api.itglue.com/developer/). The generated document is [ITGlue.yaml](ITGlue.yaml).

The scraper extracts documented endpoints, descriptions, parameters, and error responses. The specification is best-effort and is not maintained or endorsed by IT Glue or Kaseya.

## Generate locally

Requires Python 3.12 or newer.

```powershell
python -m pip install -r requirements.txt
python docs-to-yaml.py
```

The generated OpenAPI version is `1.0.0.YYYYMMDD`, using the UTC generation date. The output is validated before atomically replacing `ITGlue.yaml`.

To select a different output path or documentation URL:

```powershell
python docs-to-yaml.py --output ITGlue.yaml --source-url https://api.itglue.com/developer/
```

## Tests

```powershell
python -m unittest discover -v
```

## GitHub Actions

The workflow runs daily, on pushes to `main`, and on manual dispatch. It tests the parser, regenerates `ITGlue.yaml`, and commits the artifact only when it changes.