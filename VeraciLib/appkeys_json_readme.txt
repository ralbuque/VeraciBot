ATENÇÃO: 

Para o projeto funcionar, você precisa ter acesso a API do X (antigo twitter), a API do OpenAI (ChatGPT) e a um banco de dados SQL SERVER.
Você pode criar uma conta no site oficial de cada um e gerar as chaves necessárias no X e na OpenAI.
As chaves devem ser colocadas no arquivo appkeys.json, que deve estar na mesma pasta deste arquivo readme.txt.	
Esse arquivo appkeys.json não é versionado no github para não expor as chaves.
Também é necessário uma conexão com banco de dados SQL Server, que pode ser local ou remoto.
SendGrid é uma API da Twilio para envio de e-mails, você pode criar uma conta gratuita e gerar a chave de API.

O formato do arquivo deve ser o a seguir:

==========appkeys.json===========
{

  "xClientId": "<<CLIENT_ID>>",
  "xClientSecret": "<<CLIENT_SECRET>>",
  "xApiKey": "<<API_KEY>>",
  "xApiSecret": "<<API_SECRET>>",
  "xAccessToken": "<<ACCESS_TOKEN>>",
  "xAccessSecret": "<<ACCESS_SECRET>>",
  "xBearerToken": "<<BEARER_TOKEN>>",

  "xUserId": "<<ID>>",
  "xUserName": "<<USER_NAME>>",

  "openAIKey": "<<OPEN_AI_API_KEY>>",
    
  "sendGridKey": "<<SEND_GRID_API>>",

  "dbConnection": "<<SQL_SERVER_DNS>>"

}
================================