"""Install Kokoro's offline English int8 model and voice pack."""

from download_kokoro import ROOT, download_model


FILES = {
    "kokoro-v1.0.int8.onnx": 114119327,
    "voices-v1.0.bin": 28214398,
}


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    for name, size in FILES.items():
        download_model(name, size)
    print(f"English Kokoro files installed in {ROOT}", flush=True)


if __name__ == "__main__":
    main()
