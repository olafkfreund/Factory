{ pkgs, ... }: {
  # TFactory integration/api lane: a REAL service dependency, provisioned
  # ephemerally and locally (no cloud). devenv `services` make this first-class.
  packages = [ pkgs.postgresql ];

  services.postgres = {
    enable = true;
    listen_addresses = "127.0.0.1";
    initialDatabases = [ { name = "appdb"; } ];
  };

  # `devenv test` starts services -> runs this -> tears down. Uses the devenv-
  # provided $PGHOST/$PGPORT (it picks a free port, e.g. 5433) rather than
  # hardcoding 5432.
  enterTest = ''
    echo "[verify] waiting for postgres on $PGHOST:$PGPORT ..."
    until pg_isready -h "$PGHOST" -p "$PGPORT" -q; do sleep 0.5; done
    echo "[verify] querying the managed DB (integration-lane proof):"
    psql -h "$PGHOST" -p "$PGPORT" -d appdb -c 'select 1 as integration_ok;'
  '';
}
