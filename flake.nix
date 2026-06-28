{
  description = "Factory program hub — dev shell for tooling (YAML/JSON validation, GitHub CLI, Python linting)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs =
    { self, nixpkgs }:
    let
      # The Factory hub is the spec/contract + docs home; this shell carries the
      # lightweight tooling the helper scripts and maintenance tasks need, so
      # nothing has to be installed system-wide. Add packages here as needed.
      forAllSystems = nixpkgs.lib.genAttrs [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
        "x86_64-darwin"
      ];
    in
    {
      devShells = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          # Python with the libraries the scripts use (stdlib covers json/urllib;
          # pyyaml is needed to validate workflow/compose YAML, requests for HTTP).
          pythonEnv = pkgs.python3.withPackages (
            ps: with ps; [
              pyyaml
              requests
            ]
          );
        in
        {
          default = pkgs.mkShell {
            packages = [
              pythonEnv
              pkgs.jq # JSON wrangling
              pkgs.yq-go # YAML on the CLI
              pkgs.ruff # Python lint/format (matches the repos' gate)
              pkgs.gh # GitHub CLI
              pkgs.git
              pkgs.curl
            ];

            shellHook = ''
              echo "Factory dev shell — python3(+pyyaml,requests), jq, yq, ruff, gh"
            '';
          };
        }
      );
    };
}
