
import express from 'express';
const app = express ();
app.use(express.json());
import * as cheerio from "cheerio"
import axios from "axios"
const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
  console.log("Server Listening on PORT:", PORT);
});
var list = {
   
   };

async function geturl(){
  var html = "";
  await axios("https://anoboy.icu/anime-list/").then((response) => {
  html = response.data;
})

var $ = cheerio.load( html );

   $("p.OnGoing a").each( function(x,y){
   
 
   var url = $(this).attr("href") 
   var tt = $(this).html()
   //var strim =  aneps(url)
   list["n"+x] = {}

   
   if( x > 2){
   
   return false }
   
console.log("ok")
	  

async function aneps() {

	  var html = "";

  await axios(url).then((response) => {
  html = response.data;
})

   var $ = cheerio.load( html );

	
	var a = "";
	
		
    $("ul.lcp_catlist a:contains('[')").remove()
    /*
	  if( $("span.pages").html() != null ){
	    var f = $("span.pages").text().slice(-1)
	    for(var i = 0;i <= f; i++){
	  	$ = Cheerio.load(geturl(x+"page/"+i), null, false);
	
		$("div.column-content a:contains('[')").remove()
	
		
	$("div.column-content a").each( function(i,va){
    
    if($(this).find("h3").html() != null ){
    
  a += `\n<div class="col-4"><button class="eps btn border text-center text-truncate p-1" data-eps="${  $(this).attr("href") }">
    Episode ${ $(this).find("h3").html().split("Episode ")[1] }
    </button></div>\n`
    }
      
      
     
    })
	  }
	  } else {
	  */
	  $("ul.lcp_catlist a").each(function(i,va){

        if( $(this).html() != null ){
  a += `\n<div class="col-4"><button class="eps btn border text-center text-truncate p-1" data-eps="${  $(this).attr("href") }">
    Episode ${ $(this).html().split("Episode ")[1] }
    </button></div>\n`
   }
      
     
    })
	  // }
	  
	
	var strim = `
    cback({ 
            "eps": ${ JSON.stringify(a) },
            
          });
    `
    
       list["n"+x][tt] = {url,strim}
}


console.log(tt)

aneps()
})

}
geturl()

app.get("/", async (req, res) => {
    try {
      //const data = await $.html();
      return res.status(200).json(
        list
      );
    } catch (err) {
      return res.status(500).json({
        err: err.toString(),
      });
    }
});