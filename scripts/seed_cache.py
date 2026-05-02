from pathlib import Path


def main() -> None:
    data_dir = Path(__file__).resolve().parents[1] / "backend" / "data" / "cached"
    print(f"Seed cache placeholder. Populate files in {data_dir} with verified demo findings.")


if __name__ == "__main__":
    main()
