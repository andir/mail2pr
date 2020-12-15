{ pkgs ? import (import ./nix/sources.nix).nixpkgs { } }:
pkgs.poetry2nix.mkPoetryApplication {
  pname = "mail2pr";
  version = "0.0.1";
  src = ./.;
  projectDir = ./.;
  nativeBuildInputs = [ pkgs.poetry ];
}
