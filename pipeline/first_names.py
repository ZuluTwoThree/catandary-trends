"""Given names for the person-name grounding check (pipeline.grounding, #11).

A capitalised bigram "Vorname Nachname" is only treated as a PERSON when its
first token is one of these given names (or follows a title/role such as CEO,
Minister, Dr.). The list is the trigger, not the verdict: the verdict is
whether every word of the name stands in the source text.

Coverage: German, English, French, Spanish, Italian, Portuguese, Dutch,
Scandinavian, Polish/Czech/Hungarian, Russian/Ukrainian (romanised), Turkish,
Arabic/Persian (romanised), Hebrew, Indian, Chinese (pinyin), Japanese and
Korean (romanised), Greek, African. ~2,400 entries, lowercase, compared
case-insensitively against the body token.

Deliberately EXCLUDED — given names that are also everyday words, months,
places or brands and would fire on "Will Europe follow?", "May 2026",
"Morgan Stanley", "Madison Square", "Paris Agreement", "Mercedes Benz",
"Lincoln Center", "Jordan Brand", "Hudson Yards", "Chase Bank", "Grace period":
will may june april august march summer autumn bill mark grace hope faith art
sun rose chase hunter max chance amber crystal jade sky storm rain dawn eve joy
reed ray lance frank grant miles pat ruby van wade rob jack don earl gene guy
jay lee rich rod warren chip buck cliff clay dale glen heath holly ivy laurel
olive pearl robin sage sierra violet georgia virginia carolina paris florence
chelsea brooklyn austin jordan israel india kenya asia china morgan stanley
eli (Eli Lilly) abu (Abu Dhabi) hong (Hong Kong)
madison lincoln kennedy hudson jackson franklin hamilton marshall wilson
nelson carter parker cooper mason logan taylor tyler bailey harrison dean
sterling gordon baker mercedes tesla ernst christian german reagan angel
forrest river brook ocean winter shell victor ford wells scott cameron
douglas graham murray ross wallace kelly kerry regan riley avery quinn
harper piper blake brady drew reese ryan sawyer spencer wesley ashton
kingston milan siena vienna. Those people are still caught when the body
writes them after a title ("CEO Will Smith").
"""
from __future__ import annotations

_RAW = """
aaron abbas abby abdel abdul abdullah abel abigail abraham abu_ achim ada adam
adan addison adel adele adeline adelheid adnan adolf adrian adriana adrienne
agatha agnes agnieszka agustin ahmad ahmed aidan aiko aileen aimee aisha akira
alain alan alba albert alberto albrecht aldo alec alejandra alejandro aleksander
aleksandr alena alessandra alessandro alex alexa alexander alexandra alexandre
alexei alexis alfons alfonso alfred alfredo ali alice alicia alina aline alison
alissa allan allen allison alma alois alonso alvaro alvin alyssa amadeus amal
amalia amanda amar amaya amelia amelie amin amina amir amit amy ana anastasia
anatoly anders andre andrea andreas andrei andres andrew andy anette angela
angelica angelika angelina angelo angus anika anita anja anke ann anna annabel
annalena anne annegret annelie annemarie annette annie annika anouk anselm
anthony antje antoine anton antonella antonia antonio anwar april_ arash arda
ariana ariane ariel arjun arlene armand armando armin arnaud arne arnold aron
arthur arturo arvid arwen asha ashley ashok astrid athanasios aubrey audrey
augusto aurelia aurelie aurelio aurora ava avi axel ayaan ayla aylin ayse azra
babette barack barbara barbra barnaby barry bart bartholomew bartosz basil
bastian beat beate beatrice beatrix beatriz becky bela ben benedetta benedict
benedikt benito benjamin benno benoit bent bernard bernd bernhard bernie bert
berta bertha bertrand beth bethany bettina betty beverly bianca bilal birgit
birte bjoern bjorn blanca bob bobby bogdan boris brad bradley bram brandon
brenda brendan brent brett brian bridget brigitte britta brittany bruce bruno
bryan burak burkhard byron caitlin caleb callum calvin camila camille candice
cara carina carl carla carlo carlos carly carmen carol carola carole carolin
carolina_ caroline carolyn carsten casey cassandra catalina caterina catharina
catherine cathy cecile cecilia cecily cedric celeste celia celine cem cesar
cezary chad chandra chantal charlene charles charlie charlotte chiara chloe
chris christa christel christiane christina christine christoph christophe
christopher chuck cindy claire clara clarence clarissa claude claudia claudio
claus clemens clement cleo clive colin colleen connie connor conrad constanze
consuelo cora coral corey corinna corinne cornelia cornelius cosima courtney
craig cristian cristiano cristina cyril cyrus dagmar daisy dalia damian damien
damon dan dana daniel daniela daniele danielle danilo danny daphne dario darius
darren daryl dave david davide davina dawid debbie deborah declan deepak
delia delphine demetrios denis denise dennis derek desmond detlef diana diane
diego dieter dietmar dietrich dilara dima dimitri dimitrios dina dirk dmitry
dolores domenico dominic dominik dominika dominique donald donna dora doreen
doris dorothea dorothy doug dustin dwight dylan eberhard ebru ed eddie edgar
edith edmund edouard eduard eduardo edward edwin efe egon eileen ekaterina
elaine eleanor elena eleni eleonora eli_ elias elif elijah elin elina elisa
elisabeth elise eliza elizabeth elke ella ellen ellie elliot elliott elmar
eloise elsa else elton elvira emanuel emanuele emil emilia emiliano emilie
emilio emily emma emmanuel emmanuelle emre enrico enrique enzo eric erica erich
erik erika erin erkan erna ernesto erwin esma esra esteban estelle esther ethan
etienne eugen eugene eugenia eugenio eva evan evelyn evelyne ewa ewald ezra
fabian fabio fabrice fabrizio fadi faisal falk fanny farah farhan farid fatima
fatma federica federico felicia felicitas felipe felix ferdinand fergus fernanda
fernando filip filippo finn fiona flavia flavio florian floyd francesca
francesco francis francisca francisco francois frank_ franka franz franziska
frauke fred freddie frederic frederick frederik frida frieda friedrich fritz
gabi gabriel gabriela gabriele gabriella gabrielle gaetano gail garrett gary
gaspard gaston gavin geneva genevieve geoffrey georg george georges georgia_
georgina gerald geraldine gerard gerd gerda gerhard germaine gero gerrit gert
gertrud gertrude giacomo gian giancarlo gianluca gianna gianni gideon gilbert
giles gill gillian gina gino giorgio giovanna giovanni gisela giselle giulia
giulio giuseppe gloria goran gordon_ gottfried grace_ graciela greg gregor
gregory greta gretchen gudrun guido guillaume guillermo gunnar gunter gunther
gus gustav gustavo gwen gwendolyn hakan hal hamid hamza hanna hannah hannelore
hannes hanno hans hansjoerg harald harold harriet harry hartmut harvey hasan
hassan hauke hayden hayley hazel heather hedwig heidi heike heiko heiner heinrich
heinz helen helena helene helga helmut henning henri henrietta henrik henry
herbert hermann hermine herve hilary hilda hildegard hilke hiroshi holger homer
horst howard hubert hugh hugo humberto husna hussein ian ibrahim ida idris igor
ilka ilona ilse ilya imke immanuel ina ines inga ingeborg inge ingo ingrid
irene irina iris irma irmgard isaac isabel isabella isabelle isadora isak ismail
isolde israel_ ivan ivana ivo ivonne jacek jack_ jackie jacob jacqueline jacques
jaime jakob jakub james jamie jan jana jane janet janice janina janine janis
janusz jared jarek jasmin jasmine jason jasper javier jay_ jayden jean jeanette
jeanne jeff jeffrey jelena jenna jennifer jenny jens jeremy jerome jerry jesse
jessica jesus jill jim jimmy jitka joachim joan joana joanna joanne joao joaquin
jochen jodie jody joe joel joerg johan johann johanna johannes john johnny jon
jonah jonas jonathan joost jordi jorge jose josef josefine joseph josephine
josh joshua josie juan juana juanita judith judy jule jules julia julian
juliana juliane julie julien juliet julio julius june_ juergen jurgen justin
justine justus kaan kai kaja kalle kamil kamila kara karel karen karim karin
karina karl karla karolina karoline karsten kasia kaspar kasper kat katarina
katarzyna kate katharina katherine kathleen kathrin kathryn kathy katia katie
katja katrin katy kay kaya keith kelly_ ken kendra kenji kenneth kenny kent
kerem kerstin kevin khalid khalil kian kiara kilian kim kimberly kira kirk kirsten
kirstin klaas klara klaus knut konrad konstantin konstantinos kristen kristian
kristin kristina kristof kristoffer krzysztof kurt kyle kylie lamar lara larissa
lars laura laure laurel_ lauren laurence laurent laurenz lavinia lawrence lea
leah leander leandro leif leila lena lennart lennox leo leon leona leonard
leonardo leonie leonor leopold leroy leslie lester leticia letizia levent levi
lewis lia liam liana lidia liliana lilian lilli lilly lily lin lina linda linus
lionel lisa lisbeth lise liv livia liz lloyd logan_ lois lola loredana lorena
lorenz lorenzo loretta lori lothar lotta lotte lou louis louisa louise lourdes
luana luc luca lucas lucia lucian luciana luciano lucie lucien lucille lucy
ludger ludovic ludwig luigi luis luisa luise lukas luke luna lutz lydia lynn
maarten madeleine madeline mads mae magda magdalena maggie magnus mahmoud maike
maja malcolm malik malin malte manfred manon manuel manuela mara marc marcel
marcela marcella marcello marcia marcin marco marcos marcus mareike maren
margaret margarete margarita margit margot margret marguerite maria mariam
marian mariana marianne maribel marie mariella marietta marija marika marilyn
marina marino mario marion marisa marita marius mariusz marjorie marko markus
marlene marlon marta martha martijn martin martina martine marvin mary maryam
mathias mathieu mathilde matilda matt matteo matthew matthias matthieu maud
maureen maurice mauricio maurizio mauro maxim maximilian maximiliano maxime
maya mechthild megan mehmet meike melanie melinda melissa melvin mercedes_
meret merle merlin merve meryem mia micaela michael michaela michael michel
michele micheline michelle miguel mika mikael mike mikhail mila milan_ milena
miles_ millie milo milos mina minh miranda mireille miriam mirjam mirko mirna
mirko mitchell mohamed mohammad mohammed moira molly mona monica monika monique
morgan_ moritz morten moses mostafa muhammad murat mustafa myra myriam nabil
nadia nadine nadja nancy naomi natalia natalie natascha natasha nathalie nathan
nathaniel naveen neil nele nelly nesrin nico nicola nicolas nicole nicolette
nigel nikita niklas niko nikola nikolai nikolaj nikolaus nikos nils nina nino
noah noel noemi nora norbert noreen norma norman nour nuria octavia odile olaf
ole oleg olga oliver olivia olivier omar ophelia orhan orlando oscar oskar ossi
oswald otto ove owen ozan pablo paloma pamela paola paolo pascal pascale
patricia patrice patricia patrick patty paul paula paulina pauline pavel pedro
peggy penelope pepe percy pere perry pete peter petra phil philip philipp
philippe philippa phoebe pia pierre pietro piotr pippa priya quentin quirin
rachel rafael rafaela raffaele raffaella rahel rahul raimund raina rainer raj
rajesh ralf ralph ramon ramona randall randy raoul raphael raphaela raquel
rasmus raul ravi raymond rebecca rebekka regina reginald reiner reinhard
reinhold remi remo renata renate rene renee reto reuben rex rhonda ricardo
riccardo richard rick rico rita roald robert roberta roberto robin_ rocco
roderick rodney rodolfo rodrigo roger roland rolf roman romana romeo romy ron
ronald ronja ronny rosa rosalie rosalind rosanna rosemarie rosemary rosie
rosina roswitha roxana roy ruben rudi rudolf rudolph rudy rupert ruth ruthie
ryan_ sabine sabrina sadie sahar said sally salma salome salvador salvatore sam
samantha samir samuel sandra sandrine sandro sandy sanjay santiago sara sarah
sascha sasha saskia saul sean sebastian sebastiano sebastien selin selina selma
serena serge sergei sergey sergio seth seyma shane shannon sharon shaun sheila
shirley sibylle siegfried sigrid silke silvana silvia silvio simon simona
simone sina sinan sindy siobhan slavko sofia sofie sol solange sonia sonja
sophia sophie soren stan stanislaw stefan stefania stefanie stefano steffen
steffi stella stephan stephane stephanie stephen steve steven stuart sue sunil
susan susana susanne susi suzanne sven svenja svetlana sybille sydney_ sylvia
sylvie tabea tabitha tadeusz tamara tami tania tanja tanya tara tarek tatiana
tatjana ted teresa teodoro terrence terry tess tessa thaddeus thea thekla
thelma theo theodor theodora theodore theresa therese thibault thierry thilo
thomas thora thorsten tiago tiffany till tilman tim timm timo timothy tina tino
titus tobias todd tom tomas tomasz tommy toni tony torben torsten tracy travis
trevor tristan trudy tyrone udo ulf uli ulla ulrich ulrike ulysses uma umberto
ursula urs ute uwe valentin valentina valentine valeria valerie valery vanessa
vera verena veronica veronika veronique vicente vicky victoria_ viktor viktoria
vince vincent vincenzo viola violeta virginie vito vittoria vittorio vivian
viviane vivienne vladimir volker waldemar walter waltraud wanda wendy werner
wilfried wilhelm wilhelmina willi william willy wilma winfried wolf wolfgang
wolfram xavier xenia yann yannick yasmin yasmine yannis yolanda yusuf yves
yvonne zachary zara zeynep zoe zofia zoltan zora
aditya ajay akash amitabh ananya anil anjali ankit arjun_ arnav arun aryan
ashish ayesha bhavna deepika dev dhruv divya gaurav gita gopal harish ishaan
jyoti kabir kapil karan kavita kiran krishna kunal lakshmi lalit madhav manish
manoj meera mohan mukesh naveen_ neha nikhil nisha nitin pankaj pooja prakash
pranav prasad pratik priyanka rahul_ rajiv rakesh ramesh rani ravi_ rekha
riya rohan rohit sachin sameer sanjay_ sanjeev shiv shreya siddharth smita
sneha sonal sudha sunita suresh swati tanvi tarun varun venkat vijay vikas
vikram vinay vinod vishal vivek yash
wei li_ ming hua jun fang lei jing yan ying xin yu hui min feng qiang ping
xiaoming xiaohong zhiwei jie yong tao hong_ bo lin_ gang bin liang yang chen_
xiang guo hao jian mei lan ling na qing rui shan ting wen xia xue yi yun zhen
zhang_ zhou_ wang_ hiroshi_ takeshi kenji_ akira_ yuki yuko yumi haruto sota
ren riku hina yui aoi sakura mei_ kaito yuto ichiro jiro taro kazuki daiki
naoki satoshi masashi hideo hideki kenta shota takashi tomoko keiko naoko
ayumi kaori megumi mayumi minjun seojun jiho jiwoo minseo jimin sooyoung
yuna seoyeon eunji hyunwoo jihoon sungmin jaehyun donghyun seungmin
ahmed_ mahmoud_ mohamed_ youssef yasser omar_ tarek_ hossam khaled sami
nadia_ leila_ rania dalia_ heba mona_ hana huda nour_ yasmin_ salma_ amira
farida karim_ walid ziad rami fadi_ bassam nabil_ samir_ adel_ ayman hisham
maher mazen wael hamid_ reza parisa shirin darius_ cyrus_ navid arash_ kamran
babak farhad mehdi hossein kian_ nima sina_ soheil roya sahar_ maryam_ mahsa
elnaz negar niloufar setareh
kwame kofi kwesi yaw ama akosua abena adwoa chidi chika emeka ngozi obi
oluwaseun tunde femi bola yemi adebayo ayo kemi funke tobi chioma ifeoma
uche nnamdi ikenna thabo sipho lerato nomvula naledi zanele mandla bongani
themba tshepo palesa lindiwe amara

aage aksel alvar anders_ anni ansgar arvid_ asger bengt birger bjarne bo_ brita
carsten_ dagny einar eirik elin_ ellinor elsa_ emil_ erlend eskil espen frode
geir gudrun_ gunnar_ gustaf haakon halvard hannu harri henrik_ hjalmar ingvar
ingrid_ jaakko jari jarl johanne jorgen jussi kaisa kalle_ karin_ kjell knud
lasse leif_ lennart_ linnea maja_ malin_ marit mattias mikko morten_ niklas_ nils_
oddvar olav oona pekka per petter ragnar rasmus_ rolf_ rune sigrid_ signe sigurd
solveig staffan stig svein sven_ tarja thorvald tobias_ torbjorn tore tove trygve
ulla_ vidar viggo yngve
bram_ daan dirk_ eline femke floris gijs hendrik huub jaap jelle joris koen
lars_ lieke lotte_ luuk maarten_ marieke marloes niels noor pieter roos ruud
sanne sjoerd sven stijn teun thijs tijn wouter
agata aleksandra alicja andrzej aneta anna_ bartek beata bogusław bożena
czesław dariusz dorota edyta elżbieta ewelina grzegorz halina hanna_ irena
iwona jacek_ jadwiga jakub_ janusz_ jarosław jerzy joanna_ jolanta kamil_
karol katarzyna_ krystyna krzysztof_ leszek lucjan łukasz maciej małgorzata
marek marian_ mariola mateusz michał mirosław monika_ natalia_ paweł piotr_
przemysław rafał renata_ robert_ ryszard sławomir stanisław sylwia tadeusz_
tomasz_ urszula waldemar_ wiesław wojciech zbigniew zofia_ zuzanna
adela bohumil ctibor dagmar_ dana_ eliška františek hana_ ivana_ jana_ jaroslav
jiří josef_ kateřina lenka lucie_ ludmila marcela_ martina_ michaela_ milan_
miroslav monika_ ondřej pavel_ pavla petr petra_ radek renáta stanislav šárka
tereza tomáš václav věra vladimír zdeněk
ágnes andrás attila balázs bence csaba dániel dóra erzsébet eszter ferenc gábor
gergely györgy imre istván jános józsef judit katalin krisztina lászló márta
mihály miklós nóra péter réka sándor tamás tibor zoltán_ zsófia zsolt zsuzsanna
andreas_ anastasios antonis christos dimitra dimitris eleftheria elena_ evangelos
georgios giannis ioanna ioannis katerina konstantina kostas kyriakos maria_
michalis nikolaos panagiotis petros sofia_ spyros stavros stefanos theodoros
vasilis yiannis
ahmet ali_ aslı ayşe aylin_ barış berk beyza bilge burcu büşra can canan cem_
cemal ceren defne deniz derya dilek ebru_ ece elif_ emine emre_ engin erdem
esra_ fatih fatma_ ferhat fikret gizem gökhan gül gülşen hakan_ halil hande
hasan_ hatice hülya ibrahim_ ilker ipek irem ismail_ kaan_ kadir kemal kerem_
leyla mehmet_ melis merve_ mert mesut murat_ mustafa_ nazlı nihat nur oğuz
okan onur orhan_ osman ozan_ özge özlem pelin recep selin_ semih serkan sevgi
sibel sinan_ tolga tuğba tuncay ufuk umut volkan yasemin yıldız yusuf_ zehra
adriano alessia alexandre_ aline_ amanda_ ana_ anderson andré antônio beatriz_
bruna bruno_ caio camila_ carla_ carlos_ cláudia cristiane daniela_ davi diego_
eduardo_ fábio felipe_ fernanda_ fernando_ gabriel_ gustavo_ guilherme heitor
helena_ henrique isabela jéssica joão_ jorge_ josé júlia juliana_ larissa_ leandro_
leonardo_ letícia lucas_ luciana_ luiz luísa manuela_ marcelo márcia marcos_
mariana_ marina_ mateus matheus miguel_ natália nuno patrícia paulo pedro_ rafael_
renato ricardo_ roberto_ rodrigo_ rui sofia_ tatiane thiago tiago_ vinícius
vitor
abe abigail_ adrian_ alan_ albert_ alfie amelia_ archie arthur_ barney beatrice_
bernadette callum_ carys cerys ciaran cillian colm conor cormac darragh
declan_ dermot dylan_ eamon eoin fergal finnian gareth gavin_ gethin gwyneth
harriet_ hugh_ ieuan imogen iolo isla jenna_ keira kieran lorcan maeve mairead
niall niamh oisin orla padraig patrick_ rhys rhiannon roisin ronan saoirse
seamus sean_ shane_ sinead siobhan_ tadhg teagan
abe_ alexis_ allison_ amber_ amy_ andrea_ angela_ anthony_ ashley_ barbara_
beverly_ bonnie brenda_ brittany_ bryce caleb_ candace carl_ carol_ carrie
cassidy chad_ charlene_ cheryl christy cindy_ claudia_ clint cody colleen_
connor_ corey_ courtney_ curtis cynthia dale_ dallas dana_ danielle_ darlene
darren_ dawn_ debbie_ denise_ dennis_ derek_ diane_ donna_ doreen_ doris_
dorothy_ dwayne earl_ elaine_ eleanor_ elmer ernest ethel eugene_ evelyn_
felicia_ florence_ frances gail_ gary_ gerald_ gertrude_ gladys glenn gloria_
gregory_ harold_ harvey_ hazel_ heather_ helen_ herbert_ homer_ howard_ irene_
jared_ jason_ jeanette_ jeffrey_ jennifer_ jeremy_ jerry_ jesse_ jessica_
jimmy_ joanne_ jodi joel_ joseph_ joyce judith_ judy_ julie_ justin_ karen_
kathleen_ keith_ kelsey kenneth_ kevin_ kimberly_ kirk_ kristen_ kyle_ larry
latoya lauren_ laurie leonard_ leroy_ leslie_ lillian linda_ lindsay lloyd_
lois_ lonnie loretta_ lori_ lorraine lucille_ luther lynn_ mabel marcia_
margaret_ marjorie_ marlene_ martha_ marvin_ maureen_ maurice_ melvin_ michele_
mildred milton minnie mitchell_ monica_ nancy_ naomi_ nathaniel_ nicole_ norma_
norman_ pamela_ patricia_ patsy paula_ pauline_ peggy_ penny phyllis priscilla
ralph_ randall_ randy_ raymond_ rebecca_ regina_ rhonda_ rodney_ roger_ ronald_
rosemary_ russell ruth_ sally_ samantha_ sandra_ sandy_ sharon_ sheila_ shelby
sheldon sherri shirley_ stacey stacy stanley_ stephanie_ steven_ stuart_ sue_
susan_ suzanne_ sylvia_ tammy tanya_ teresa_ terrence_ terry_ theresa_ thomas_
tiffany_ timothy_ tina_ todd_ tonya tracy_ travis_ trevor_ troy tyrone_ vanessa_
velma vernon vicki victor_ vincent_ virginia_ vivian_ wallace_ walter_ wanda_
wayne wendell wendy_ wesley_ whitney wilbur willard willie wilma_ yvette
yvonne_ zachary_
avi_ avraham ayelet batya benny chaim dana_ david_ dov eitan eli_ eliezer elior
gal gideon_ gil hadar hila idan ilan itai itamar liat lior maayan meir menachem
michal moshe nadav netanel nir noa noam ofer ofir omer oren ori rivka ronen roni
shai shira shlomo shmuel tal tamar tomer uri yael yair yaron yehuda yigal yishai
yoav yonatan yossi yuval ziv
aigars andris arturs edgars gatis inese ingars janis juris kristaps laima liene
maris raimonds ruta valdis andrius aurelija darius_ dovile egle gediminas
giedrius jonas_ jurgita kestutis laura_ mantas mindaugas rasa rimas rita_
ruta_ saulius tomas_ vytautas zivile
aleksa ana_ andrej anica bojan branko dalibor danijela dejan dragan dragana
draško dubravka dušan goran_ gordana igor_ ivan_ ivana_ jelena_ jovan jovana
katarina_ lazar ljiljana luka marija_ marko_ milica milos_ mirjana nemanja
nenad nikola_ nina_ predrag radovan sanja saša slobodan snežana sonja_ srdjan
stefan_ tamara_ tijana vesna vladan vuk zoran zorica željko
"""

# Entries with a trailing underscore are documented as excluded in the module
# docstring (ambiguous with words/places/brands) and are dropped here.
FIRST_NAMES: frozenset[str] = frozenset(
    w for w in _RAW.split() if not w.endswith("_")
)
