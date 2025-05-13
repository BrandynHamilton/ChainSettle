STATUS_MAP = {
    'unverified':0,
    'confirmed':1,
    'failed':2
}

BLOCK_EXPLORER_MAP = {
    'ethereum':'https://sepolia.etherscan.io/tx/',
    'base':'https://base-sepolia.blockscout.com/tx/',
    'blockdag':'https://primordial.bdagscan.com/tx/'
}

SUPPORTED_NETWORKS = ['ethereum','blockdag','base']
SUPPORTED_APIS = ['plaid', 'github', 'paypal']