from __future__ import annotations
import hashlib, hmac, json, os, time
from .profile_store import mark_paid

def verify_signature(payload:bytes, header:str, secret:str, tolerance:int=300):
    parts={}
    for bit in (header or '').split(','):
        if '=' in bit:
            k,v=bit.split('=',1); parts.setdefault(k,[]).append(v)
    if not parts.get('t') or not parts.get('v1'): raise ValueError('missing Stripe signature fields')
    ts=int(parts['t'][0])
    if abs(int(time.time())-ts)>tolerance: raise ValueError('stale Stripe webhook signature')
    signed=str(ts).encode()+b'.'+payload
    expected=hmac.new(secret.encode(),signed,hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected,v) for v in parts['v1']): raise ValueError('invalid Stripe signature')

def handle(payload:bytes, signature:str):
    secret=os.environ.get('STRIPE_WEBHOOK_SECRET','')
    if not secret: raise RuntimeError('STRIPE_WEBHOOK_SECRET not configured')
    verify_signature(payload,signature,secret)
    event=json.loads(payload)
    if event.get('type')!='checkout.session.completed': return {'accepted':True,'ignored':True}
    obj=event.get('data',{}).get('object',{})
    if obj.get('payment_status')!='paid': return {'accepted':True,'ignored':True}
    email=(obj.get('customer_details') or {}).get('email') or obj.get('customer_email')
    checkout=obj.get('id')
    if not email or not checkout: raise ValueError('paid checkout missing email or session id')
    profile_id,_=mark_paid(email,checkout,'stripe')
    return {'accepted':True,'profile_id':profile_id}
