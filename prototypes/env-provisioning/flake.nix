{
  description = "RFC-0005 prototype: per-task toolchain devShells + daemonless OCI sandbox images";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };

      # The RFC-0005 Environment Manifest selects a toolchain set per spec language.
      # This map is the prototype stand-in for that manifest -> packages resolution.
      toolchains = {
        rust   = [ pkgs.cargo pkgs.rustc ];
        go     = [ pkgs.go ];
        python = [ pkgs.python312 pkgs.uv ];
      };

      # materialize-or-HALT proof commands (RFC-0005 evidence gate)
      proofs = {
        rust = "cargo --version && rustc --version";
        go = "go version";
        python = "python3 --version";
      };

      # Daemonless, layered OCI image containing exactly the toolchain — this is the
      # per-task ephemeral "factory-sandbox" image the coder/test runner would launch.
      mkImage = name: tools: pkgs.dockerTools.streamLayeredImage {
        name = "factory-sandbox-${name}";
        tag = "latest";
        contents = tools ++ [ pkgs.bashInteractive pkgs.coreutils pkgs.git ];
        config.Cmd = [ "${pkgs.bashInteractive}/bin/bash" ];
      };
    in {
      # `nix develop .#<lang>` materializes the toolchain (Tier A provisioning)
      devShells.${system} =
        builtins.mapAttrs (n: tools: pkgs.mkShell { packages = tools; }) toolchains;

      # `nix build .#image-<lang>` builds the per-task sandbox OCI image
      packages.${system} =
        (builtins.listToAttrs (map (n: {
          name = "image-${n}";
          value = mkImage n toolchains.${n};
        }) (builtins.attrNames toolchains)))
        // { default = pkgs.writeText "proofs" (builtins.toJSON proofs); };
    };
}
