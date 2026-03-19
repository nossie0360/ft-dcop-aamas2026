import pathlib

import rsa
from rsa import PublicKey, PrivateKey

KEY_LENGTH = 1024
SHARED_KEY_LENGTH = 32

def write_keys(path: pathlib.Path):
    """Generates a single RSA key pair and writes them to files.

    This function creates one RSA key pair and saves it to the specified directory.
    Public key is stored in 'default_public.key' and private key in
    'default_private.key'.

    The keys are stored in a custom comma-separated format.

    Note:
        This function is intended for simulation purposes and is not secure for
        use in production environments.

    Args:
        path (pathlib.Path): The directory where the key files will be stored.
    """
    import secrets
    pub_key, priv_key = rsa.newkeys(KEY_LENGTH)
    shared_key = secrets.token_bytes(SHARED_KEY_LENGTH)
    public_key_str = f"{pub_key.n},{pub_key.e}"
    private_key_str = f"{priv_key.n},{priv_key.e},{priv_key.d},{priv_key.p},{priv_key.q}"

    public_key_path = path / "default_public.key"
    private_key_path = path / "default_private.key"
    shared_key_path = path / "default_shared.key"

    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)

    public_key_path.write_text(public_key_str)
    private_key_path.write_text(private_key_str)
    shared_key_path.write_bytes(shared_key)

def read_public_key(path: pathlib.Path) -> PublicKey:
    """
    Reads the default public key from a file.

    This function reads a public key from 'default_public.key' in the
    specified directory.

    Note:
        This function is intended for simulation purposes.

    Args:
        path (pathlib.Path): The directory where the key file is located.

    Returns:
        PublicKey: The default PublicKey object.

    Raises:
        FileNotFoundError: If the specified key file does not exist.
        ValueError: If the key file is not in the expected format.
    """
    public_key_path = path / "default_public.key"
    try:
        public_key_str = public_key_path.read_text()
    except FileNotFoundError:
        raise FileNotFoundError(f"Public key file not found at {public_key_path}")
    try:
        n, e = map(int, public_key_str.split(","))
        return PublicKey(n, e)
    except (ValueError, IndexError):
        raise ValueError(f"Invalid public key format in {public_key_path}: {public_key_str}")

def read_private_key(path: pathlib.Path) -> PrivateKey:
    """
    Reads the default private key from a file.

    This function reads a private key from 'default_private.key' in the
    specified directory.

    Note:
        This function is intended for simulation purposes.

    Args:
        path (pathlib.Path): The directory where the key file is located.

    Returns:
        PrivateKey: The default PrivateKey object.

    Raises:
        FileNotFoundError: If the specified key file does not exist.
        ValueError: If the key file is not in the expected format.
    """
    private_key_path = path / "default_private.key"
    try:
        private_key_str = private_key_path.read_text()
    except FileNotFoundError:
        raise FileNotFoundError(f"Private key file not found at {private_key_path}")
    try:
        n, e, d, p, q = map(int, private_key_str.split(","))
        return PrivateKey(n, e, d, p, q)
    except (ValueError, IndexError):
        raise ValueError(f"Invalid private key format in {private_key_path}: {private_key_str}")

def read_shared_key(path: pathlib.Path) -> bytes:
    """
    Reads the default shared key from a file.

    This function reads a shared key from 'default_shared.key' in the
    specified directory.

    Note:
        This function is intended for simulation purposes.

    Args:
        path (pathlib.Path): The directory where the key file is located.

    Returns:
        bytes: The default shared key as bytes.

    Raises:
        FileNotFoundError: If the specified key file does not exist.
    """
    shared_key_path = path / "default_shared.key"
    try:
        return shared_key_path.read_bytes()
    except FileNotFoundError:
        raise FileNotFoundError(f"Shared key file not found at {shared_key_path}")


if __name__ == '__main__':
    p = pathlib.Path() / 'config' / 'keys'
    write_keys(p)
    print(read_private_key(p))
    print(read_public_key(p))
    print(read_shared_key(p))
