import json
import os
import boto3
from s3kv import S3KeyValueStore
from openai import OpenAI

from botocore.exceptions import NoCredentialsError

openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

system_prompt = """
        Assume that you are a car dealer assistant that responds in markdown format. A customer is interested in buying a car and may have selected a vehicle, check conversation history to verify. Your goal is to negotiate and upsell long term finance and insurance product offerings for the  Vehicle. In case the customer declines a service, creatively ask for the reason and capture the answers for the  manager for review.
    
        The following product offerings are available with their costs terms and average repair cost:
            - Extended Warranty / Vehicle Service Contract : cost is $1999.00 for 36 months and average repair cost is $3200.00.
            - Pre-paid Maintenance Contract : cost is $1999.00 for 36 months and average repair cost is $4500.00.
            - GAP Insurance (Standard): cost is $1199.00 for 36 month and average cost for claim is $3000.00.
            - Tire & Wheel Protection (with Cosmetric coverage) : cost is $1936.00 for 36 months and average repair cost is $3000.00.
            - Tire & Wheel Protection : cost is $1466.00 for 36 months and average repair cost is $2500.00.
            - Dent Protection : cost is $410.00 for 36 months and average repair cost is $2000.00.
            - Key Replacement : cost is $270.00 for 36 months and average replacement cost is $1000.00.
            - Windshield Protection : cost is $262.00 for 36 months and average replacement cost is $3500.00.
            - Stolen Vehicle Tracking and Recovery System : cost is $1000.00 for 36 months and average replacement is cost of vehicle itself

        Your goal is sell the appropriate product offerings to the customer. The chances of the customer buying a product depends on: 
            1. How long customer intends to be the car owner. If customer is planning to be a long term owner then customer would be interested in extended warranty.
            2. customer's intended vehicle usage: commuting or weekend driving. customer may be interesting in Tire and Wheel protection, windshield protection, and dent & ding protection. 
            3. Is cutomer worried about crime in the area? or is located in a city where Crime is High? if yes, they might be interested in Stolen Vehicle Tracking and Recovery System coverage
            4. Is the customer located in a city where Roads are Bad, they might be intersted in Tire & Wheel Protection, Dent Protection and Windshield Protection coverage.
            5. Offer GAP Insurance and Key Replacement insurance to the customer if they want to finance the vehicle.

        Crime and Road Statistics by city are as follows:
            - Chicago, Crime=Low, Roads=Good, 11.21% crime below compared to national average
            - New York, Crime=Low, Roads=Good, 19.07% crime below compared to national average
            - Los Angeles, Crime=Low, Roads=Bad, 40.33% crime below compared to national average
            - California, Crime=High, Roads=Good, 27.38% crime above compared to national average
            - Washington, Crime=Low, Roads=Good, 51.57% crime below compared to national average
            - Miami, Crime=High, Roads=Bad, 48.91% crime above compared to national average
            - Phoenix, Crime=Medium, Roads=Good, 4.50% crime below compared to national average
            - St Louis, Crime=High, Roads=Bad, 33.98% crime above compared to national average
            - San Diego, Crime=Low, Roads=Good, 45.71% crime below compared to national average
            - Bel Air, Crime=Low, Roads=Good, 11.21% crime above compared to national average
            - Calabasas, Crime=High, Roads=Good, 23.55% crime above compared to national average             

        Please ask customer terse questions to get this information if the information has been provided show in summarized form and if user asks for details then show the average cost to repair/replace with crime rate and road conditions. Using this information, please show the average monthly cost for these products, and also ask the customer if they are interested in knowing more about specific product offerings, mentioning the products based on customer's info, in the form of terse questions. If customer asks a question in response, reply from the information given in this prompt. Please feel free to ask questions to the customer to get the information needed to select the products.
    
        Always stay in character as a  car dealer assistant. Be terse in your answers but with all relevant information in summarized form. Always sell the Pre-paid Maintenance Contract with all sales. Limit to only 3 products provided to customer in summarized form, display costs at first. 

        """


def system_message():
    messages = [
            {"role": "system", "content": system_prompt}
        ]
        
    return messages

def lambda_handler(event, context):
    
    bucket_name = os.environ.get("CONVERSATION_BUCKET")
    kvstore = S3KeyValueStore(bucket_name)
    
    body = json.loads(event['Records'][0]['Sns']['Message'])
    
    #print("Complete Event Dump Below:")
    #print(event)
    
    
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
        
    #print(message, user, params, connection_id, conversation_id)
    
    # initialize WebSocket
    ws_client = boto3.client('apigatewaymanagementapi', 
                          endpoint_url=f"https://{request_context['domainName']}/{request_context['stage']}",
                          region_name=os.environ['AWS_REGION'])
    
    llm_response = None
    chat_response_chunk = None
    chat_response = ''
    coversation_start = {'content': '__START__'}
    coversation_end = {'content': '__END__'}
    
    #print("Messages: "+str(messages))

    try:
        llm_response = openai_client.chat.completions.create(messages=messages 
                                            ,model= 'gpt-3.5-turbo-0125' #'gpt-4-0125-preview'  #'gpt-3.5-turbo-0125'
                                            ,stream=True
                                            ,
                                            )
        ws_client.post_to_connection(ConnectionId=connection_id, Data=json.dumps({'conversation_id': conversation_id, 'role': 'assistant', 'text': coversation_start}))                                    
        for chunk in llm_response:
            if chunk.choices[0].delta.content!=None:
                print('chunk: ', chunk)
                chat_response_chunk = {'content': chunk.choices[0].delta.content} 
                chat_response = chat_response+chunk.choices[0].delta.content
                ws_client.post_to_connection(ConnectionId=connection_id, Data=json.dumps({'conversation_id': conversation_id, 'role': 'assistant', 'text': chat_response_chunk}))
        ws_client.post_to_connection(ConnectionId=connection_id, Data=json.dumps({'conversation_id': conversation_id, 'role': 'assistant', 'text': coversation_end}))
        messages.append({"role": "assistant", "content": chat_response})
        kvstore.put_value(user, conversation_id, messages)
        #print("Complete Chat Response: "+ chat_response)
        #print("LLM Response: "+llm_response)
                                            
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