
import express from 'express';
const app = express ();
app.use(express.json());
import * as cheerio from "cheerio"
import axios from "axios"
const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
  console.log("Server Listening on PORT:", PORT);
});
var url = "https://anoboy.icu"

var $ = ""

var data = ""
function rep(str, obj) {
  for (const x in obj) {
    str = str.replace(new RegExp(x, 'g'), obj[x]);
  }
  return str;
}
async function geturl(x){

var html = "";
  await axios( x ).then((response) => {
  html = response.data;
 })
return html

}

function rex(x,y,z,a){

if( a == "ok"){

         $(x).each( function(){
          if( $(this).attr(y) != undefined){
             if( !$(this).attr(y).startsWith("http") ){
    
                 $(this).attr(y , z+$(this).attr(y) )
    
             } else {
             
             let qq = $(this).attr(y).replace(url, "http://localhost:3000")
             $(this).attr(y , qq )
             
             }
          }
      })
      
      } else {

      $(x).each( function(){
          if( $(this).attr(y) != undefined){
             if( !$(this).attr(y).startsWith("http") ){
    
                 $(this).attr(y , z+$(this).attr(y) )
    
             }
          }
      })
    }
  }
    
function core(){

    $("script[type='application/ld+json'], div[id^='ad'], #judi, #judi2, #disqus_thread, .sidebar, #coloma").remove()
    rex("link", "href", url)
    rex("script", "src", url)
    rex("img", "src" ,url)
    rex("amp-img", "src" ,url)
    rex("iframe", "src" ,url)
    rex( "a", "href" , "http://localhost:3000","ok")
  $(".footercopyright").append(`
  <style>
  #menu,   div.column-three-fourth  { width:100% !important;
           overflow: hidden;
          }

  
  </style>
  `)
}


app.get("/", async (req, res) => {
    $ = cheerio.load( await geturl( url ) );
    core()
    /*
    $("link").each( function(){
    
    if( !$(this).attr("href").startsWith("https:") ){
    
    $(this).attr("href" , url+$(this).attr("href") )
    
    }
    
    })
    */

    try {
      
      return res.status(200).send(
         $.html()
      );
    } catch (err) {
      return res.status(500).json({
        err: err.toString(),
      });
    }
});

app.get('/:key*', async (req, res) => {

   var j = url+"/"+req.params.key+req.params[0]
   
   $ = cheerio.load( await geturl( j ),null, false );
   core()
  
  try {

    res.send( $.html() );
  } catch (error) {
    console.error(error);
    res.status(500).send(req.params);
  }
});
