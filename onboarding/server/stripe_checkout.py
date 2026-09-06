from __future__ import annotations
import json, os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

def create_core_checkout():
    secret=os.environ.get('STRIPE_SECRET_KEY','').strip()
    price=os.environ.get('JK_STRIPE_CORE_PRICE_ID','').strip()
    base=os.environ.get('JK_PUBLIC_BASE_URL','').rstrip('/')
    if not secret or not price or not base:
        raise RuntimeError('Stripe checkout is not configured')
    body=urlencode({
      'mode':'payment',
      'line_items[0][price]':price,
      'line_items[0][quantity]':'1',
      'success_url':base+'/onboarding/?session_id={CHECKOUT_SESSION_ID}',
      'cancel_url':base+'/#pricing',
      'billing_address_collection':'required',
      'customer_creation':'always',
      'metadata[jackknife_flow]':'managed-office-setup-v1',
    }).encode()
    req=Request('https://api.stripe.com/v1/checkout/sessions',data=body,headers={
      'Authorization':'Bearer '+secret,
      'Content-Type':'application/x-www-form-urlencoded',
      'User-Agent':'JackKnifeOnboarding/1.0',
    },method='POST')
    with urlopen(req,timeout=15) as r:
        out=json.loads(r.read())
    if not out.get('id') or not out.get('url'): raise RuntimeError('Stripe did not return a checkout session')
    return {'checkout_session_id':out['id'],'checkout_url':out['url']}
