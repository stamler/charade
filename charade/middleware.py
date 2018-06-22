# middleware
# Basic Azure ActiveDirectory JWT Token Validation

import jwt
import falcon
import time
import requests
import logging
from .database import db_obj
from cryptography.x509 import load_pem_x509_certificate as load_cert
from cryptography.hazmat.backends import default_backend
from urllib.parse import urlsplit


# The Authentication and Authorization section of the app.
# Load keys from Microsoft and cache them for refresh_interval before reloading
# If there is no token, only OPTIONS requests will be served
# AUTHENTICATION
#   If there is a token, confirm it is valid (signed by Microsoft AzureAD)
#   If the token is valid, confirm it is for this tenant
# AUTHORIZATION
#   If the token is for this tenant, load user's permissions (from Roles?)
#   If the request is not within these permissions deny it, otherwise serve response
# AzureAD Token Reference is available here:
# https://docs.microsoft.com/en-us/azure/active-directory/develop/active-directory-token-and-claims
class AzureADTokenValidator(object):
    def __init__(self,tenant_name,app_id,refresh_interval=3600):
        self.app_id = app_id
        self.tenant_name = tenant_name
        self.log = logging.getLogger(__name__)
        self.log.addHandler(logging.NullHandler())

        # These requests are permitted regardless of the token
        self.exempt_methods = ['OPTIONS']

        # Time in seconds to keep cached keys from Microsoft
        self.key_refresh_interval = refresh_interval

        self._load_certificates()

    # Get the token signing keys from Microsoft and store them in self.keys,
    # a dict with 'kid' as the key and cert as the value
    def _load_certificates(self):
        self.last_refresh = int(time.time())
        res = requests.get('https://login.microsoftonline.com/' +
                    self.tenant_name + '/.well-known/openid-configuration')
        res = requests.get(res.json()['jwks_uri'])
        self.keys = {}
        for key in res.json()['keys']:
            x5c = key['x5c']
            cert = ''.join([ '-----BEGIN CERTIFICATE-----\n', x5c[0],
                                            '\n-----END CERTIFICATE-----\n' ])
            public_key = load_cert(cert.encode(),
                                   default_backend()).public_key()
            self.keys[key['kid']] = public_key

    # Return decoded token claims if valid. Otherwise raise exception
    def authenticate(self, auth_header):
        if (auth_header):
            access_token = auth_header.partition('Bearer ')[2]
        else:
            #TODO: Ensure this is in JSON API format (it's not right now)
            # Also make sure Content-Type header is correct per docs
            # http://falcon.readthedocs.io/en/stable/api/errors.html
            raise falcon.HTTPUnauthorized("No authorization header provided.")

        # reload the keys if they're stale
        if (int(time.time()) - self.last_refresh > self.key_refresh_interval):
            self._load_certificates()

        if(access_token):
            token_header = jwt.get_unverified_header(access_token)

            if (token_header['kid'] in self.keys):
                public_key = self.keys[token_header['kid']]

                # validate the token against the public_key and the app_id
                try:
                    decoded = jwt.decode(access_token, public_key,
                                         algorithms = token_header['alg'],
                                           audience = self.app_id)
                                        # should validate issuer, nonce,
                                        # audience, nbf, etc..
                    expiry = time.strftime('%Y-%m-%d %H:%M:%S',
                                                time.localtime(decoded['exp']))
                    self.log.debug("Token is valid until {}".format(expiry))
                    return decoded
                except jwt.InvalidTokenError as e:
                    #TODO: Ensure this is in JSON API format (it's not right now)
                    # Also make sure Content-Type header is correct per docs
                    # http://falcon.readthedocs.io/en/stable/api/errors.html
                    raise falcon.HTTPUnauthorized("Provided token is invalid: {}".format(e))
            else:
                #TODO: Ensure this is in JSON API format (it's not right now)
                # Also make sure Content-Type header is correct per docs
                # http://falcon.readthedocs.io/en/stable/api/errors.html
                raise falcon.HTTPUnauthorized("Provided token signed by an "
                                              "unrecognized authority.")
        else:
            #TODO: Ensure this is in JSON API format (it's not right now)
            # Also make sure Content-Type header is correct per docs
            # http://falcon.readthedocs.io/en/stable/api/errors.html
            raise falcon.HTTPUnauthorized("No token provided.")

    # Raise an exception if the authenticated token doesn't
    # have privileges for the requested resource.
    def authorize(self, claims, req):
        # AzureAD includes group claims in the token if the manifest contains
        # groupMembershipsClaims with value of "SecurityGroup" or "All" 
        security_groups = claims['groups']

        # In order to search the database for the correct permissions we 
        # need to get a standard format for resource_name from the request.
        # Unless a baseURL is specified (not implemented) this is the
        # first non-empty segment of the "path" component returned by the
        # urlsplit() method of urllib.parse available in Python 3.
        # urlsplit() and urlparse() retain the leading slash in the
        # https://docs.python.org/3/library/urllib.parse.html#urllib.parse.urlparse
        # path component raising some issues:
        # 1. If we're going to do a split() with a '/' delimiter then the
        #    first element in the resulting list will be an empty string. 
        # 2. The URL may contain multiple consecutive slashes since it is 
        #    not normalized
        # 3. The database stores 'resources' with a leading slash included
        #    so that the root url can contain text (just a '/') so after 
        #    splitting we have to tack a leading slash back on prior to
        #    querying the DB for permissions
        # 
        # IFF in the future we decide to support a baseURL (i.e. netloc + a
        # path segment(s) goes before resource name) then we would count
        # the number of path segments in that baseURL when it is set and add 
        # that number to the index so that we can accurately extract the name
        # of the resource.
        #
        # The solution is to do a split against slash delimiters, remove empty
        # strings, then take element at index 0 + (baseURL path segment count),
        # falling back to the root url if there are no non-empty path segments
        path = urlsplit(req.uri).path
        try:
            res = '/' + [r for r in path.split('/') if r != ''][0]
        except IndexError:
            res = '/'
        self.log.debug("Method: {} Resource: {}".format(req.method, res))

        # Get the list of groups allowed to use this method on
        # this resource and store it in authorized_groups[]
        APIRequests = db_obj.resources['APIRequests']['sqla_obj']
        Permissions = db_obj.resources['Permissions']['sqla_obj']
        query = db_obj.get_session().query(Permissions.group_oid).\
                    join(APIRequests).\
                    filter(APIRequests.verb == req.method).\
                    filter(APIRequests.resource == res)
        # Each result is a named tuple, even for just one column 
        # so we flatten into a list of strings (note the comma: g,)
        authorized_groups = [g for g, in query]

        # Return success if at least one of the group claims in the
        # provided token is in the authorized_groups list, otherwise
        # raise a 403 Forbidden HTTP Error Status  
        for g in security_groups:
            if g in authorized_groups:
                self.log.debug("Group {} is allowed in authorized: {}".format(
                    g, authorized_groups
                ))
                return
        raise falcon.HTTPForbidden("You are not allowed to do this.")

    def process_request(self, req, resp):
        # Next line necessary because CORS plugin isn't activated in exception situation
        #resp.set_header('Access-Control-Allow-Origin', '*')

        self.log.debug("Headers: {}".format(req.headers))

        if (req.method in self.exempt_methods):
            return

        auth_header = req.get_header('Authorization')

        # This will raise falcon.HTTPUnauthorized if it fails
        claims = self.authenticate(auth_header)

        # This will raise falcon.HTTPForbidden if it fails
        self.authorize(claims, req)


class CORSComponent(object):
    def process_response(self, req, resp, resource, req_succeeded):
        resp.set_header('Access-Control-Allow-Origin', '*')

        if (req_succeeded
            and req.method == 'OPTIONS'
            and req.get_header('Access-Control-Request-Method')
        ):

            allow = resp.get_header('Allow')
            resp.delete_header('Allow')

            allow_headers = req.get_header(
                'Access-Control-Request-Headers',
                default='*'
            )

            resp.set_headers((
                ('Access-Control-Allow-Methods', allow),
                ('Access-Control-Allow-Headers', allow_headers),
                ('Access-Control-Max-Age', '86400'),  # 24 hours
            ))

# https://developers.google.com/web/fundamentals/performance/optimizing-content-efficiency/http-caching
class CacheController(object):
    def process_response(self, req, resp, resource, req_succeeded):
        safe_methods = ['GET', 'OPTIONS', 'HEAD']
        if (req_succeeded and req.method in safe_methods):
            resp.cache_control = ['max-age=10']
