### Proposição de sistema: monitoramento ubíquo de saúde

1. COMPREENSÃO DO PROBLEMA
 Usando a proposta de monitoramento e assistência a uma pessoa idosas, podemos criar o seguinte sistema ubíquo:

O sistema físico é implementado no lugar em que um idoso reside, mas profissionais de saúde/a família com acesso ao sistema também são usuários do sistema pela via digital. 

É preciso que os sinais físicos do usuário sejam captados pelo sistema, o ambiente precisa ter conexão confiável e garantia do funcionamento dos sensores específicos e o sistema deve oferecer feedback sobre funcionamento e nível de baterias de suas partes.

Os dispositivos são uma roupa inteligente (para os sinais físicos), dispositivo móvel e um servidor remoto, a comunicação entre roupa inteligente e dispositivo móvel é bluetooth (fallback: internet) e entre dispositivo móvel e servidor via internet

As informações são processadas na borda inicialmente e depois distribuída para o servidor centralizado.

O maior risco vem na rejeição do idoso à roupa inteligente ou falha em conexões do dispositivo móvel

2. MODELAGEM DO SISTEMA
   PDF do repositório para o fluxo.

  Esse sistema é ubíquo e a mudança de contexto que pode modificar o funcionamento do sistema é a alteração de sinais vitais ou detecção de erro nas partes do sistema, que pode ser de malfuncionamento dos sensores ou nível de bateria.
