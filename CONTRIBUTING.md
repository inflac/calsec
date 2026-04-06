# Contribute

First off, thanks for taking the time to contribute!

## Setup Development Environment

1. Clone the repository
2. Create a virtual Python environment inside the project folder:

    ```bash
    python3 -m venv .venv
    ```

3. Install the Python requirements:

    ```bash
    pip3 install -r requirements.txt
    ```

4. **Optional: Install pandoc**

    The "Build & Package" task uses pandoc to convert `README.md` and `WHITEPAPER.md` into `.html` files that are included in the release ZIP. Without pandoc, the raw `.md` files are included instead.

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ -v --cov=gui --cov-report=term-missing
```

VS Code tasks for both are available under **Terminal → Run Task**.

## Release Signing

Release binaries are signed with an Ed25519 key via GitHub Actions. The signing step requires the `RELEASE_SIGNING_KEY` secret to be set in the repository settings. Local builds skip the signing step — the sign script (`scripts/sign_release.py`) reads the key exclusively from the `RELEASE_SIGNING_KEY` environment variable and will fail if it is not set.

To generate a new signing keypair:

```bash
python scripts/gen_signing_key.py
```

Add the private key output to GitHub Secrets as `RELEASE_SIGNING_KEY`, and paste the public key into `_RELEASE_PUBLIC_KEY_PEM` in `gui/updater.py`.
