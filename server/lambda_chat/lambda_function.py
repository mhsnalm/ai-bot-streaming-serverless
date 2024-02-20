import json
import os
from openai import OpenAI

from botocore.exceptions import NoCredentialsError
import boto3

openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def lambda_handler(event, context):
    body = json.loads(event['Records'][0]['Sns']['Message'])
    print("Complete Event Dump")
    print(event)
    
    # print("Message Body Dump")
    # print(body)
    
    request_context = body['requestContext']
    connection_id = request_context['connectionId']

    prompt = 'You are a helpful assistant who is professional and courteous. Your responses are formatted in markdown.' #body['payload']['prompt']
    messages = body['payload']['messages']
    params = body['payload']['params']
    msgid = body['payload']['msgid']
    
    print(prompt, messages, params, connection_id, msgid)
    
    # Send message to WebSocket
    ws_client = boto3.client('apigatewaymanagementapi', 
                          endpoint_url=f"https://{request_context['domainName']}/{request_context['stage']}",
                          region_name=os.environ['AWS_REGION'])
    
    llm_response = None
    chat_response = None
    
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
                chat_response = {'content': chunk.choices[0].delta.content} 
                ws_client.post_to_connection(ConnectionId=connection_id, Data=json.dumps({'msgid': msgid, 'role': 'assistant', 'text': chat_response}))
        ws_client.post_to_connection(ConnectionId=connection_id, Data=json.dumps({'msgid': msgid, 'role': 'assistant', 'text': '[DONE]'}))
                                            
        # chat_response = {'content': llm_response.choices[0].message.content} 
    except Exception as error:
        print(json.dumps({'error': str(error)}))
        chat_response = {'content': str(error) + '|' + str(error)}
        return {
                    'statusCode': 500,
                    'body': json.dumps(chat_response)
                }
    
    # print('response:', chat_response)
    
    # input_data = {
    #     'ConnectionId': connection_id,
    #     'Data': json.dumps({'msgid': msgid, 'text': chat_response})
    # }
    
    # try:
    #     ws_client.post_to_connection(ConnectionId=input_data['ConnectionId'], Data=input_data['Data'])
    # except NoCredentialsError:
    #     print('Credentials not available')
    #     return {
    #         'statusCode': 500,
    #         'body': json.dumps({'error': 'Credentials not available'})
    #     }

    return {
        'statusCode': 200,
    }