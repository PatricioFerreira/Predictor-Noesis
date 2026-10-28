
function setUpTextoBoletim()
{
	$("#dlgTextoBoletimCadastro").dialog(
			{
				resizable: true,
				height: 500,
				width: 800,
				autoOpen: false,
				modal: false,
				close: CloseFunction,
				scroll: hideAll
			}
		);
		
}

function closeTextoBoletim(){
	 hideAll();
	$("#dlgTextoBoletimCadastro").dialog("close");	
}

function clickButtonArquivoTextoBoletim(com,grid) {
	
}

function clickButtonTextoBoletim(com,grid)
{
	if (com=='Excluir')
	{
		var ids = getGridId(grid);
		if (ids){
			excluirTextoBoletim(ids,com,grid);
		}else{
			jError("Selecione ao menos um item da listagem.", 'Aten\u00e7\u00e3o');
		}
		
	}else if (com=='Novo')
	{
		abreTextoBoletim().complete(function(){bindFields();});
	}			
}


function abreTextoBoletim()
{
	setUpTextoBoletim();
	 $.get("telas/publicacao/textoBoletim/textoBoletimCadastro.html",
		function(data)
		{
			$("#dlgTextoBoletimCadastro").html( data );	
			$("#dlgTextoBoletimCadastro").dialog("open");
			
			 var myNicEditor = new nicEditor({fullPanel : true});
	          myNicEditor.setPanel('TextoBoletim_PanelDiario');
	          myNicEditor.addInstance('TextoBoletim_textoDiario');
	          
	          var myNicEditor2 = new nicEditor({fullPanel : true});
	          myNicEditor2.setPanel('TextoBoletim_PanelExtraordinario');
	          myNicEditor2.addInstance('TextoBoletim_textoExtraordinario');
	          
	          
	          populaDadosTextoBoletim();
	          
		}).complete(function(){bindFields();});
	
}

function insereNumeroTextoBoletim(){
	
	jNumber('Informe um n\u00famero para subistituir: {num}', '', 'N\u00famero para boletim: ' , function(resp) {
	    if( resp ) {
	    	$('#TextoBoletim_texto').html($('#TextoBoletim_texto').html().replace('{num}',resp))
	    }
	});
}

function populaDadosTextoBoletim() {

	var fn = function(bean) {
		if (bean.length>0){
			$('#TextoBoletim_id').val(bean[0].id);
			$('#TextoBoletim_textoDiario').html(bean[0].textoDiario);	
			$('#TextoBoletim_textoExtraordinario').html(bean[0].textoExtraordinario);	
		}
	};
	
	TextoBoletimService.findAll({callback: fn});
}

function saveTextoBoletim() {

	var bean = {
			id:$('#TextoBoletim_id').val(), 
			textoDiario: $('#TextoBoletim_textoDiario').html(),
			textoExtraordinario: $('#TextoBoletim_textoExtraordinario').html()
	};
		
	var fn = function() {
		
		if(!$("#TextoBoletim_id").val()) {
			jAlert("Inserido com sucesso.", 'Sucesso');
		} else {
			jAlert("Atualizado com sucesso.", 'Sucesso');
		}	
		
		closeTextoBoletim();
			
	};

	TextoBoletimService.save(bean,{callback: fn});
}