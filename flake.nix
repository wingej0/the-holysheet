{
  description = "the-holysheet — school data ETL pipeline into a PostgreSQL warehouse";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        # Mirrors requirements.txt, using nixpkgs' builds instead of pip wheels
        # (psycopg2-binary / pymssql wheels don't run on NixOS without nix-ld).
        pythonEnv = pkgs.python3.withPackages (ps: with ps; [
          pandas
          requests
          sqlalchemy
          gspread
          python-dotenv
          psycopg2
          pymssql
          openpyxl # pandas.read_excel engine for the accountability extractor
        ]);

        # Runs run_etl.py from the checkout in the current directory rather than
        # a store copy: data/ paths are cwd-relative, and load_dotenv() searches
        # for .env starting from the code's own directory.
        runEtl = pkgs.writeShellApplication {
          name = "run-etl";
          runtimeInputs = [ pythonEnv ];
          text = ''
            if [ ! -f run_etl.py ]; then
              echo "run-etl: run this from the-holysheet repo root" >&2
              exit 1
            fi
            exec python run_etl.py "$@"
          '';
        };
      in
      {
        packages.default = runEtl;

        apps.default = {
          type = "app";
          program = "${runEtl}/bin/run-etl";
        };

        devShells.default = pkgs.mkShell {
          packages = [
            pythonEnv
            pkgs.postgresql # psql client for poking at the warehouse
          ];
        };
      });
}
