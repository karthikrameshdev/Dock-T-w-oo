pm.test('Local model answered successfully',()=>pm.expect(pm.response.code).to.eql(200));
pm.test('Assistant content is substantive',()=>{const result=pm.response.json();pm.expect(result.message.role).to.eql('assistant');pm.expect(result.message.content.length).to.be.above(20);pm.expect(result.message.content).not.to.include('repeat or rephrase');});
