"""Create and configure an AWS VPC and related infrastructure"""

import argparse
import logging
import boto3
from botocore.exceptions import ClientError


def create_vpc(region, cidr_block, vpc_name=None, wait=False):
    """Create an AWS VPC

    :param region: (string) AWS region, e.g., 'us-west-1'
    :param cidr_block: (string) IPv4 network range, e.g., '10.0.0.0/16'
    :param vpc_name: (string) Tag 'Name' to assign to VPC
    :param wait: (bool) Wait until VPC is available before returning
    :return: (dict) VPC information
    :raise: ClientError
    """

    # Create the VPC
    client = boto3.client('ec2', region_name=region)
    vpc = client.create_vpc(CidrBlock=cidr_block)
    vpc_id = vpc['Vpc']['VpcId']

    # Optional: Wait until VPC is available
    if wait:
        client.get_waiter('vpc_available').wait(VpcIds=[vpc_id])

    # Optional: Define a 'Name' tag
    if vpc_name is not None:
        client.create_tags(Resources=[vpc_id],
                           Tags=[
                               {
                                   'Key': 'Name',
                                   'Value': vpc_name,
                               },
                           ])

    # Enable DNS support and DNS hostnames so we can SSH into the VPC's EC2 instances using public DNS hostnames
    # Note: DNS support is enabled by default
    '''
    client.modify_vpc_attribute(VpcId=vpc_id,
                                EnableDnsSupport={'Value': True})  # Must enable DNS support first
    '''
    client.modify_vpc_attribute(VpcId=vpc_id,
                                EnableDnsHostnames={'Value': True})
    return vpc


def get_vpc_id(region, cidr_block):
    """Retrieve a VPC's ID

    :param region: (string) AWS region the VPC is located in
    :param cidr_block: (string) VPC's CIDR address block
    :return: (string) VPC ID
    :raise: ClientError if VPC was not found
    """

    client = boto3.client('ec2', region_name=region)
    vpc = client.describe_vpcs(Filters=[
        {
            'Name': 'cidr',
            'Values': [cidr_block],
        },
    ])
    # Should have matched only one VPC with the specified CIDR block
    # If VPC not found, vpc['Vpcs'] is an empty list
    if vpc['Vpcs']:
        return vpc['Vpcs'][0]['VpcId']


def create_internet_gateway(region, vpc_id, igw_name=None):
    """Create an internet gateway and attach it the the VPC

    :param region: (string) AWS region to create the internet gateway in (must be same region as VPC)
    :param vpc_id: (string) VPC ID to attach the gateway to
    :param igw_name: (string) 'Name' tag for internet gateway
    :return: (dict) Internet gateway information
    """

    # Create the internet gateway
    client = boto3.client('ec2', region_name=region)
    igw = client.create_internet_gateway()
    igw_id = igw['InternetGateway']['InternetGatewayId']

    # Optional: Define a 'Name' tag
    if igw_name is not None:
        client.create_tags(Resources=[igw_id],
                           Tags=[
                               {
                                   'Key': 'Name',
                                   'Value': igw_name,
                               },
                           ])

    # Attach the gateway to the VPC
    client.attach_internet_gateway(InternetGatewayId=igw_id,
                                   VpcId=vpc_id)
    return igw


def get_vpc_internet_gateway_id(region, vpc_id):
    """Retrieve a VPC's internet gateway ID

    :param region: (string) AWS region in which the VPC and internet gateway are located
    :param vpc_id: (string) VPC ID
    :return: (string) VPC internet gateway ID
    :raise ClientError if internet gateway was not found
    """

    client = boto3.client('ec2', region_name=region)
    igw = client.describe_internet_gateways(Filters=[
        {
            'Name': 'attachment.vpc-id',
            'Values': [vpc_id],
        },
    ])
    # Should have matched only one internet gateway attached to the VPC
    # If internet gateway not found, igw['InternetGateways'] is an empty list
    if igw['InternetGateways']:
        return igw['InternetGateways'][0]['InternetGatewayId']


def create_public_route_table(region, vpc_id, igw_id, rtb_name=None):
    """Create a public route table to assign to subnets

    A "public route table" has a public route to the internet. Subnets with a public route table can communicate
    outside the VPC to the internet. The VPC's main route table has a private route table that does not allow
    communication outside the VPC to the internet. By default, a subnet is assigned the VPC's main route table,
    thereby making the subnet private. Leaving the main route table as private and creating a second public route
    table and explicitly assigning the public table to subnets you want to be public is a best practice.

    :param region: (string) AWS region in which to create the route table (must be same region as VPC and gateway)
    :param vpc_id: (string) VPC ID
    :param igw_id: (string) Internet gateway ID
    :param rtb_name: (string) 'Name' tag for route table
    :return: (dict) Route table information
    :raise ClientError
    """

    # Create the route table
    client = boto3.client('ec2', region_name=region)
    rtb = client.create_route_table(VpcId=vpc_id)
    rtb_id = rtb['RouteTable']['RouteTableId']

    # Create a public route to the internet in the table
    response = client.create_route(RouteTableId=rtb_id,
                                   DestinationCidrBlock='0.0.0.0/0',
                                   GatewayId=igw_id)
    if not response['Return']:
        raise ClientError(
            error_response={
                'Error': {
                    'Code': 'CreateRouteError',
                    'Message': 'Could not create the route',
                }},
            operation_name='CreateRoute')

    # Optional: Define a 'Name' tag
    if rtb_name is not None:
        client.create_tags(Resources=[rtb_id],
                           Tags=[
                               {
                                   'Key': 'Name',
                                   'Value': rtb_name,
                               },
                           ])
    return rtb


def get_public_route_table_info(region, igw_id):
    """Retrieve information about the public route table associated with a VPC's internet gateway

    :param region: (string) AWS region in which the route table is located
    :param igw_id: (string) Internet gateway ID
    :return: (dict) Information about the public route table
    :raise ClientError
    """

    client = boto3.client('ec2', region_name=region)
    rtb = client.describe_route_tables(Filters=[
        {
            'Name': 'route.gateway-id',
            'Values': [igw_id],
        },
    ])
    # Should have matched only one public route table associated with the VPC's internet gateway
    # If the public route table was not found, rtb['RouteTables'] is an empty list
    if rtb['RouteTables']:
        return rtb['RouteTables'][0]


def create_subnet(region, vpc_id, subnet_cidr_block, subnet_name=None):
    """Create a subnet in a specified VPC

    By default, the subnet is associated with the default route table which is a private route table,
    thereby making the subnet private. To make the subnet public, associate it with a public route table.

    :param region: (string) AWS region in which to create the subnet
    :param vpc_id: (string) VPC ID to create the subnet in
    :param subnet_cidr_block: (string) Subnet's IPv4 CIDR block
    :param subnet_name: (string) 'Name' tag for subnet
    :return: (dict) Subnet information
    """

    # Create the subnet
    client = boto3.client('ec2', region_name=region)
    subnet = client.create_subnet(VpcId=vpc_id,
                                  CidrBlock=subnet_cidr_block)

    # Optional: Define a 'Name' tag
    if subnet_name is not None:
        client.create_tags(Resources=[subnet['Subnet']['SubnetId']],
                           Tags=[
                               {
                                   'Key': 'Name',
                                   'Value': subnet_name,
                               },
                           ])
    return subnet


def associate_public_route(region, rtb_id, subnet_id):
    """Associate a public route table to a subnet, making the subnet public

    The setting 'auto-assign public IP address on EC2 launch' is also enabled for
    any EC2 instances launched in the subnet.

    :param region: (string) AWS region with the route table and subnet
    :param rtb_id: (string) ID of public route table
    :param subnet_id: (string) ID of subnet
    :return: (string) Association ID. Used subsequently to dissociate route table.
    """

    # Associate the route table with the subnet
    client = boto3.client('ec2', region_name=region)
    association = client.associate_route_table(RouteTableId=rtb_id,
                                               SubnetId=subnet_id)

    # Enable auto-assign public IPv4 address to any EC2 instances started in this subnet
    client.modify_subnet_attribute(SubnetId=subnet_id,
                                   MapPublicIpOnLaunch={'Value': True})
    return association['AssociationId']


def get_subnets(region, vpc_id):
    """Retrieve information about a VPC's subnets

    :param region: (string) AWS region of the VPC and subnets
    :param vpc_id: (string) VPC ID
    :return: (list) Information about all subnets
    """

    # Get information about the VPC's subnets
    client = boto3.client('ec2', region_name=region)
    subnets = client.describe_subnets(Filters=[
        {
            'Name': 'vpc-id',
            'Values': [vpc_id],
        },
    ])
    # Assume all subnets were returned, i.e., subnets['NextToken'] is not defined
    # Return list of subnets
    return subnets['Subnets']


def delete_vpc_resources(region, cidr_block):
    """Delete the AWS resources allocated for the VPC

    :param region: (string) AWS region in which the VPC is located
    :param cidr_block: (string) VPC's CIDR block
    :raise ClientError
    """

    # Retrieve the VPC's ID
    vpc_id = get_vpc_id(region, cidr_block)
    if vpc_id is None:
        # VPC not found, nothing to delete
        return
    client = boto3.client('ec2', region_name=region)

    # Retrieve the VPC's internet gateway ID
    igw_id = get_vpc_internet_gateway_id(region, vpc_id)
    if igw_id is not None:
        # Delete the public route table to the internet, including any tags
        rtb = get_public_route_table_info(region, igw_id)
        if rtb is not None:
            # Disassociate the route table from subnets
            for association in rtb['Associations']:
                client.disassociate_route_table(AssociationId=association['RouteTableAssociationId'])
            rtb_id = rtb['RouteTableId']
            client.delete_tags(Resources=[rtb_id])
            client.delete_route_table(RouteTableId=rtb_id)

        # Delete any gateway tags
        client.delete_tags(Resources=[igw_id])

        # Detach the gateway from the VPC and then delete it
        client.detach_internet_gateway(InternetGatewayId=igw_id,
                                       VpcId=vpc_id)
        client.delete_internet_gateway(InternetGatewayId=igw_id)

    # Retrieve the VPC's subnets
    subnets = get_subnets(region, vpc_id)
    for subnet in subnets:
        # Delete the subnet and its tags
        subnet_id = subnet['SubnetId']
        client.delete_tags(Resources=[subnet_id])
        client.delete_subnet(SubnetId=subnet_id)

    # Delete the VPC and its tags
    client.delete_tags(Resources=[vpc_id])
    client.delete_vpc(VpcId=vpc_id)


def main():
    """Exercise the VPC methods"""

    # Set these values before running
    region = 'us-west-1'
    vpc_name = 'vpc-boto3'  # Optional: For no VPC name, set to None
    cidr_block = '10.1.0.0/16'  # 65,536 IP addresses
    subnet01_cidr_block = '10.1.0.0/28'  # 16 IP addresses - 5 reserved by AWS
    subnet01_name = 'subnet-boto3-01-public'
    subnet02_cidr_block = '10.1.1.0/28'  # 16 IP addresses - 5 reserved by AWS
    subnet02_name = 'subnet-boto3-02-private'
    igw_name = 'igw-boto3'  # Optional: For no internet gateway name, set to None
    rtb_name = 'rtb-boto3-public'

    # Set up logging
    logging.basicConfig(level=logging.DEBUG,
                        format='%(levelname)s: %(asctime)s: %(message)s')

    # Process command-line arguments
    arg_parser = argparse.ArgumentParser(description='AWS VPC Example')
    arg_parser.add_argument('-d', '--delete', action='store_true',
                            help='delete allocated resources')
    args = arg_parser.parse_args()
    delete_resources = args.delete
    logging.debug(f'delete_resources={delete_resources}')

    # Delete the allocated VPC resources?
    if delete_resources:
        try:
            delete_vpc_resources(region, cidr_block)
        except ClientError as e:
            logging.error(e)
            exit(1)
        logging.debug(f'Deleted VPC {vpc_name}(CIDR block: {cidr_block})')
        exit(0)

    # Create a VPC
    try:
        vpc = create_vpc(region, cidr_block, vpc_name, wait=True)
    except ClientError as e:
        logging.error(e)
        exit(1)
    vpc_id = vpc['Vpc']['VpcId']
    logging.debug(f'Created VPC {vpc_name}(ID: {vpc_id})')

    # Create an internet gateway and attach it to the VPC
    try:
        igw = create_internet_gateway(region, vpc_id, igw_name)
    except ClientError as e:
        logging.error(e)
        exit(1)
    igw_id = igw['InternetGateway']['InternetGatewayId']
    logging.debug(f'Created internet gateway {igw_name}(ID: {igw_id}) and attached to VPC')

    # Create a route table to assign to public subnets. Associate the table to the VPC
    try:
        route_table = create_public_route_table(region, vpc_id, igw_id, rtb_name)
    except ClientError as e:
        logging.error(e)
        exit(1)
    rtb_id = route_table['RouteTable']['RouteTableId']
    logging.debug(f'Created public route table to internet')

    # Create a public subnet
    try:
        subnet01 = create_subnet(region, vpc_id, subnet01_cidr_block, subnet01_name)
    except ClientError as e:
        logging.error(e)
        exit(1)
    subnet01_id = subnet01['Subnet']['SubnetId']

    # Assign the public route table to the subnet, making the subnet public
    try:
        subnet01_association_id = associate_public_route(region, rtb_id, subnet01_id)
    except ClientError as e:
        logging.error(e)
        exit(1)
    logging.debug(f'Created public subnet {subnet01_name}')

    # Create a private subnet
    try:
        subnet02 = create_subnet(region, vpc_id, subnet02_cidr_block, subnet02_name)
    except ClientError as e:
        logging.error(e)
        exit(1)
    subnet02_id = subnet02['Subnet']['SubnetId']
    logging.debug(f'Created private subnet {subnet02_name}')

    logging.info(f'Created VPC {vpc_name} and related infrastructure')


if __name__ == '__main__':
    main()
