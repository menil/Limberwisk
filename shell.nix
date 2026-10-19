{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    git
    gh
    just
    jq
  ];

  shellHook = ''
    echo "❄️ Welcome to the My Project shell!"
  '';
}
