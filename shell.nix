{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    git
    gh
    just
    jq
    python3
    python3Packages.pytest
    python3Packages.pyyaml
    ruff
  ];

  shellHook = ''
    echo "❄️ MuteMe Flow dev shell"
  '';
}
