__author__ = 'sebastian neubauer'
import docker
import psycopg2
import time
import socket


def get_hostname():
    return socket.getfqdn()


def _docker_client():
    return docker.DockerClient(base_url='unix://var/run/docker.sock', version='auto', timeout=30)


def get_open_port():
    # this should be done somewhere else, e.g docker itself, but for now...
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("",0))
    s.listen(1)
    port = s.getsockname()[1]
    s.close()
    return port


def get_container_by_name(postgraas_instance_name):
    # return the container object or None if not found
    c = _docker_client()
    try:
        return c.containers.get(postgraas_instance_name)
    except docker.errors.NotFound:
        return None


def check_container_exists(postgraas_instance_name):
    if get_container_by_name(postgraas_instance_name):
        return True
    return False


def create_postgres_instance(postgraas_instance_name, connection_dict):
    c = _docker_client()
    environment = {
        "POSTGRES_USER": connection_dict['db_username'],
        "POSTGRES_PASSWORD": connection_dict['db_pwd'],
        "POSTGRES_DB": connection_dict['db_name']
    }
    internal_port = 5432
    if check_container_exists(postgraas_instance_name):
        raise ValueError('Container exists already')
    image = 'postgres:9.4'
    container = c.containers.create(image,
                                    name=postgraas_instance_name,
                                    ports={internal_port: connection_dict['port']},
                                    environment=environment,
                                    restart_policy={"Name": "unless-stopped"},
                                    labels={"postgraas": image})
    container.start()
    return container.id


def delete_postgres_instance(container_id):
    c = _docker_client()
    c.containers.get(container_id).remove(force=True)


def wait_for_postgres_listening(container_id, timeout=10):
    """
    Inspect/follow the output of the docker container logs until encountering the
    message from postgres that it accepts connections.

    Raises in case the container does not exist.

    Caveat: this check is specific to the used docker image.
    Tested for current postgres:9.4 image.

    :returns: boolean, whether the message has been (True), or the timeout has been hit (False).
    """
    c = _docker_client()
    cont = c.containers.get(container_id)
    for i in range(max(int(timeout * 10), 1)):
        # not very efficient to always gather all logs, but this method
        # is currently used for testing only, so it should be OK.
        output = cont.logs(stdout=True, stderr=True)
        # the startup script in the docker image starts postgres twice,
        # so wait for the second start:
        if output.count('database system is ready to accept connections') >= 2:
            return True
        time.sleep(0.1)
    return False   # pragma: no cover


def wait_for_postgres(dbname, user, password, host, port):
    """
    Try to connect to postgres every second, until it succeeds.
    """
    for i in range(540):
        try:
            conn = psycopg2.connect(dbname=dbname, user=user, password=password, host=host, port=port)
        except psycopg2.OperationalError as e:
            print i, " ..waiting for db"
            time.sleep(1)
