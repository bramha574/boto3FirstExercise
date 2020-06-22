#!/usr/bin/env python3

import boto3
import botocore
import yaml
import time
import subprocess
import os

ec2Client = boto3.client('ec2')
ec2Resource = boto3.resource('ec2')

def keyPairExists(keyName):
	try:
		keysFound = ec2Client.describe_key_pairs(KeyNames = [keyName])
		return True
	except botocore.exceptions.ClientError as e:
		return False


def create_key(keyName):
	if keyPairExists(keyName):
		print(f'Key {keyName} already Exists')
	else:
		keyPair = ec2Resource.create_key_pair(KeyName=keyName)
		print(f'New Key Created - {keyName} : FingerPrint: {keyPair.key_fingerprint}')
		with open(f'./{keyName}.pem', 'w') as file:
		    file.write(keyPair.key_material)
	
	if os.path.exists (f'{keyName}.pem') :
		os.system(f'chmod 400 {keyName}.pem')    
		sshPublicKey = subprocess.getoutput(f'ssh-keygen -y -f {keyName}.pem')
		print(f'Public key :  {sshPublicKey}')
	else:
		raise Exception(f'Please place the {keyName}.pem file in the current working dir and try running the script again')	

	return sshPublicKey


#Function to create instance
def create_instance(instanceType, securityGroupId, keyName):
	try:
		ec2_instances = ec2Resource.create_instances(
		 ImageId = 'ami-000e7ce4dd68e7a11',
		 MinCount = 1,
		 MaxCount = 1,
		 InstanceType = instanceType,##'t3a.small', # vcpu = 2 and memory = 2
		 KeyName = keyName,
		 Placement = {
		 'AvailabilityZone': 'us-east-2c'
		 },
		 UserData = userdata,
		 SecurityGroupIds=[securityGroupId]
		)

	except Exception as e:
		exception_message = f'Error creating instance. Exception : {e}'	

	newInstanceId = ec2_instances[0].id
	print (f'New instance created {newInstanceId}')
	print ("Waiting for instance to get to 'running' state.")
	waiter = ec2Client.get_waiter('instance_running')
	waiter.wait(InstanceIds=[newInstanceId])
	print (f'Instance {newInstanceId} is running now')	

	return ec2_instances[0]

#Function to create volume
def create_volume(volume_size):
	try:
		print("Creating Volume - Size : ",  volume['size_gb'])
		ebs_volume = ec2Client.create_volume(
			Size=volume['size_gb'],
			VolumeType='gp2',
			AvailabilityZone='us-east-2c'
		)

		newVolumeid = ebs_volume['VolumeId']

		waiter = ec2Client.get_waiter('volume_available')
		waiter.wait(VolumeIds=[newVolumeid])

		print (f'Volume Creation Done and it is available - {newVolumeid}')
		return newVolumeid

	except Exception as e: 
		print(f'Error creating volume. Exception : {e}')

#Function to attach instance
def attach_volume(newVolumeid, newInstanceId, deviceName):
	try: 
		ebs_volume_attach = ec2Client.attach_volume(
			VolumeId = newVolumeid,
			InstanceId = newInstanceId,
			Device = deviceName
		)

		print (f'Volume {newVolumeid} is attached to the instance {newInstanceId}')

	except Exception as e:
		print(f'Error attaching volume {newVolumeid} to instance {newInstanceId}')

#Read yaml file and store content into python objects
serverDetailsYamlFile = open("serverDetails.yaml")
parsed_ServerDetails = yaml.load(serverDetailsYamlFile, Loader=yaml.FullLoader)

instanceType = parsed_ServerDetails['server']['instanceType']
sgGroupId = parsed_ServerDetails['server']['securityGroupId']
keyName = parsed_ServerDetails['server']['keyName']
volumes = parsed_ServerDetails['server']['volumes']

userName = parsed_ServerDetails['server']['users'][0]['login']

#Create Key
public_key = create_key(keyName)

userdata = f'''#!/bin/bash
user={userName}
sudo adduser $user
sudo su $user << EOSU
mkdir /home/$user/.ssh
chmod 700 /home/$user/.ssh
touch /home/$user/.ssh/authorized_keys
chmod 600 /home/$user/.ssh/authorized_keys
echo {public_key} > /home/$user/.ssh/authorized_keys
EOSU
'''

#Create Volumes and Attach to Instance.
for volume in volumes:
	volumeType = volume['type']
	volumeMount = volume['mount']
	volumeDeviceName = volume['device']
	
	newVolumeid = create_volume(volume['size_gb'])

	userdata += f'\nmkfs -t {volumeType} {volumeDeviceName}\nmkdir -p {volumeMount}\nmount {volumeDeviceName} {volumeMount}'

#Create a new EC2 instance
newInstance = create_instance(instanceType, sgGroupId, keyName)
newInstance.load()
newInstanceId = newInstance.id
newInstancePublicDns = newInstance.public_dns_name

#Attach Volumes
for volume in volumes:
	attach_volume(newVolumeid, newInstanceId, volume['device'])
	time.sleep(10)

print("Please run the follwing commands to login after few minutes.")
print(f'ssh -i {keyName}.pem {userName}@{newInstancePublicDns}')

exit()

#ec2Resource.instances.filter(InstanceIds=[newInstanceId]).terminate()