# OTel HTTP span attribute keys used to derive observed REST relationships (spec §32).
HTTP_REQUEST_METHOD = "http.request.method"
HTTP_ROUTE = "http.route"
URL_TEMPLATE = "url.template"
SERVER_ADDRESS = "server.address"
SERVER_PORT = "server.port"
# The sole allowlisted way to resolve a CLIENT-only call's target service identity (11H R3/spec
# §7.2/§7.5) - server.address/server.port are network identifiers, never used for resolution
# (spec §7.5's "no guessing" rule).
PEER_SERVICE = "peer.service"
