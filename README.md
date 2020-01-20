# Create an AWS VPC using AWS SDK for Python

The sample program creates an AWS VPC (Virtual Private Cloud), including all necessary infrastructure, 
such as an internet gateway, route table, and one public and one private subnet. EC2 instances
and similar resources, such as load balancers, can be immediately launched in the VPC.
 
At the time of this writing, the generated VPC and infrastructure resources incur no costs, even if 
your initial free-tier time has expired.  

## Repository files

* `aws_vpc.py` : Main program source file

## AWS infrastructure resources

* VPC
* Internet gateway
* Route table
* Subnets (one public, one private)
* 'Name' tags on each resource

Note: All resources are created in the US West (N. California) `us-west-1` region. The region can be
changed by editing the `region` variable defined in the program's `main` function. Other resource settings,
such as CIDR block ranges and resource names, can be changed by reassigning variable values in `main`.

## Prerequisites

* Install Python 3.x
* Install the AWS SDK for Python `boto3`. Instructions are at https://github.com/boto/boto3.
* Install the AWS CLI (Command Line Interface). Instructions are at
  https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-install.html.
* Configure the AWS CLI. Instructions are at
  https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-getting-started.html.

## Instructions

To create the AWS VPC and related infrastructure:

    python aws_vpc.py
    
To delete the AWS VPC and related infrastructure:

    python aws_vpc.py -d | --delete
