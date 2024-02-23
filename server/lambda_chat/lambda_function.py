import json
import os
import boto3
from s3kv import S3KeyValueStore
from openai import OpenAI

from botocore.exceptions import NoCredentialsError

openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

system_prompt = f""" You are a helpful assistant """

def system_message():
    messages = [
            {"role": "system", "content": system_prompt}
        ]
        
    return messages

def lambda_handler(event, context):
    
    bucket_name = os.environ.get("CONVERSATION_BUCKET")
    kvstore = S3KeyValueStore(bucket_name)
    
    body = json.loads(event['Records'][0]['Sns']['Message'])
    
    print("Complete Event Dump Below:")
    print(event)
    
    
    request_context = body['requestContext']
    connection_id = request_context['connectionId']

    user = body['payload']['user']
    
    params = body['payload']['params']
    
    conversation_id = body['payload']['conversation_id']
    message = body['payload']['message']
    
    # check conversation history
    prev_conversation = kvstore.get_value(user, conversation_id)
    if (prev_conversation):
        messages = prev_conversation
        messages.append({"role": "user", "content": message})
    else:
        messages = system_message()
        messages.append({"role": "user", "content": message})
        
    print(message, user, params, connection_id, conversation_id)
    
    # initialize WebSocket
    ws_client = boto3.client('apigatewaymanagementapi', 
                          endpoint_url=f"https://{request_context['domainName']}/{request_context['stage']}",
                          region_name=os.environ['AWS_REGION'])
    
    llm_response = None
    chat_response_chunk = None
    chat_response = ''
    
    print("Messages: "+str(messages))

    try:
        llm_response = openai_client.chat.completions.create(messages=messages 
                                            ,model='gpt-3.5-turbo-0125'
                                            ,stream=True
                                            ,
                                            )
                                            
        for chunk in llm_response:
            if chunk.choices[0].delta.content!=None:
                print('response:', chunk.choices[0].delta.content)
                chat_response_chunk = {'content': chunk.choices[0].delta.content} 
                chat_response = chat_response+chunk.choices[0].delta.content
                ws_client.post_to_connection(ConnectionId=connection_id, Data=json.dumps({'conversation_id': conversation_id, 'role': 'assistant', 'text': chat_response_chunk}))
        ws_client.post_to_connection(ConnectionId=connection_id, Data=json.dumps({'conversation_id': conversation_id, 'role': 'assistant', 'text': '[DONE]'}))
        messages.append({"role": "assistant", "content": chat_response})
        kvstore.put_value(user, conversation_id, messages)
                                            
    except Exception as error:
        print(json.dumps({'error': str(error)}))
        chat_response = {'content': str(error) + '|' + str(error)}
        return {
                    'statusCode': 500,
                    'body': json.dumps(chat_response)
                }
    

    return {
        'statusCode': 200,
    }