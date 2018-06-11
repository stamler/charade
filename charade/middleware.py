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
                    raise falcon.HTTPUnauthorized("Provided token is invalid: {}".format(e))
            else:
                raise falcon.HTTPUnauthorized("Provided token signed by an "
                                              "unrecognized authority.")
        else:
            raise falcon.HTTPUnauthorized("No token provided.")

    # Raise an exception if the authenticated token doesn't
    # have privileges for the requested resource.
    def authorize(self, claims, req):
        method, uri = req.method, req.uri
        session = db_obj.get_session()

        # Get the user from claims
        user = session.query(db_obj.resources['Users']['sqla_obj']).filter_by(work_email=claims['upn'])

        if (user is not None):
            # user is in the database, load their roles
            #   for each role in roles look for the uri
            #       if the uri is found look for the method
            #           if the method is found
            #               return
            #   raise falcon.HTTPForbidden("user doesn't have permission")
            return
        else:
            raise falcon.HTTPForbidden("Unrecognized user")

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
