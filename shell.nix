{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    git
    gh
    just
    jq
    python3
    python3Packages.pytest
    ruff
  ];

  shellHook = ''
    echo "❄️ MuteMe Flow dev shell"
  '';
}
