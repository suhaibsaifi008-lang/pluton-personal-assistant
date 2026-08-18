# Development

Use the commands in the README to create the Python virtual environment and install frontend dependencies. Run the API from the project root, so the database is created at `data/pluton.db`.

Useful commands:

```powershell
uvicorn backend.app.main:app --reload
Set-Location frontend; npm run dev
Set-Location frontend; npm run build
```

Keep secrets only in `.env`. Never add `.env`, the database, or `node_modules` to source control.
