import base64
import hmac
import hashlib
import urllib
from urllib import parse
h = hmac.new(b"OtxrzxIsfpFjA7SwPzILwy8Bw21TLhquhboDYROV",
             b"GET\n\n\n1141889120\n/oss-example/oss-api.pdf",
             hashlib.sha1)
print(h)
print (parse.quote(base64.encodestring(h.digest()).strip()))
# urllib.quote(base64.encodestring(h.digest()).strip())