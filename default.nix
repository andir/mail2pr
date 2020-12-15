let
  sources = import ./nix/sources.nix;
  pkgs = import sources.nixpkgs {};
in pkgs.poetry2nix.mkPoetryApplication {
  pname = "mail2pr";
  version = "0.0.1";
  src = ./.;
  projectDir = ./.;

  nativeBuildInputs = [ pkgs.poetry ];
}
