import 'dart:io';
import 'dart:convert';
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:camera/camera.dart';
import 'package:http/http.dart' as http;

List<CameraDescription> cameras = [];

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    cameras = await availableCameras();
  } on CameraException catch (e){
    print('Camera error $e');
  }
  runApp(const PWrScannerApp());
}

class PWrScannerApp extends StatelessWidget {
  const PWrScannerApp({super.key});

  // This widget is the root of your application.
  @override
  Widget build(BuildContext context) {
    const Color col =  Color(0xFF9A342D);
    return MaterialApp(
      title: 'PWr Scanner',
      theme: ThemeData(
        primaryColor: col,
        appBarTheme: const AppBarTheme(backgroundColor: col),
        //colorScheme: .fromSeed(seedColor: Colors.col),
      ),
      home: const MainScreen(),
    );
  }
}

// -------------------------
// ----- EKRAN GLOWNY ------ jbc to ja napisalem serio xD
// -------------------------
class MainScreen extends StatefulWidget {
  const MainScreen({super.key});

  @override
  State<MainScreen> createState() => _MainScreenState();
}

class _MainScreenState extends State<MainScreen> {
  File? _image; // zrobione zdjecie
  String _buildingResult = "Wybierz zdjęcie lub uruchom skaner, żeby rozpoznać budynek";
  bool _isLoading = false;
  final ImagePicker _picker = ImagePicker();

  // domyslne MOJE IP
  String _serverIP = "172.20.10.4";

  @override
  void initState(){
    super.initState();
    _findServerIP(); // automatyczne znalezienie serwera przy starcie
  }

  // automatyczne IP
  Future<void> _findServerIP() async {
    try{
      var socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0);
      socket.broadcastEnabled = true;
      socket.send(utf8.encode("GDZIE_JEST_SERWER_PWR"), InternetAddress("255.255.255.255"), 9000);

      socket.listen((RawSocketEvent e) {
        Datagram? d = socket.receive();
        if (d!= null){
          String response = utf8.decode(d.data);
          setState(() {
            _serverIP = response; // IP z serwera - lets goooo
          });
          socket.close();
        }
      });
      // po 3s zamykamy jesli 0 odpowiedzi
      Future.delayed(const Duration(seconds: 3), () => socket.close());
    } catch (e) {
      print("Nie udało się wysłać broadcastu UDP");
    }
  }


  // wysylanie na serwer
  Future<void> _uploadImageToServer(File imageFile) async{
    setState(() {
      _isLoading=true;
    });

    try{
      var uri = Uri.parse('http://$_serverIP:8000/predict');

      // paczka ze zdjeciem
      var request = http.MultipartRequest('POST', uri);
      request.files.add(await http.MultipartFile.fromPath('file', imageFile.path));

      // wysylamy na serwer i czekamy na odp
      var response = await request.send();
      var responseData = await response.stream.bytesToString();
      var json = jsonDecode(responseData);


      setState(() {
        if (response.statusCode == 200){
          if (json.containsKey('error')){
            _buildingResult = "Błąd z serwera: ${json['error']}";
          } else if (json['budynek'] == "Nie rozpoznano") {
            _buildingResult = "Zbyt niska pewność, spróbuj inne ujęcie!";
          } else if (json['budynek']=="To nie jest budynek!"){
            _buildingResult = "To nie jest budynek! Nakieruj kamerę na elewację.";
          } else {
              _buildingResult = "Budynek: ${json['budynek']}\nPrawdopodobieństwo: ${(json['pewnosc']).toStringAsFixed(2)}%";     
              if (json.containsKey('wydzial')) _buildingResult += "\nWydział: ${json['wydzial']}";
          }
        } else {
          _buildingResult = "Błąd serwera. Kod: ${response.statusCode}";
        }
      });
    } catch (e) {
      setState(() {
        _buildingResult = "Błąd połączenia!\nIP: $_serverIP\nSprawdź sieć Wi-Fi.";
      });
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  Future<void> _reportError() async{
    if (_image == null) return;

    // komunikat ladowania
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Wysyłanie zgłoszenia...')));

    try {
      var uri = Uri.parse('http://$_serverIP:8000/report');
      var request = http.MultipartRequest('POST', uri);
      request.files.add(await http.MultipartFile.fromPath('file', _image!.path));

      var response = await request.send();

      if (response.statusCode == 200){
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Dziękujemy! Błąd został zgłoszony.')));
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Błąd wysyłania zgłoszenia.')));
    }
  }

  // robienie zdjecia
  Future<void> _takePhoto() async{
    final XFile? pickedFile = await _picker.pickImage(
      source: ImageSource.camera,
      imageQuality: 80,
      maxWidth: 800
    );
    if (pickedFile!=null){
      setState(() {
        _image = File(pickedFile.path);
        _buildingResult = "Analizowanie...";
      });
      await _uploadImageToServer(_image!);
    }
  }

  // wybieranie z galerii
  Future<void> _pickFromGallery() async{
    final XFile? pickedFile = await _picker.pickImage(source: ImageSource.gallery, imageQuality: 80, maxWidth: 800);
    if (pickedFile!=null){
      setState(() {
        _image = File(pickedFile.path);
        _buildingResult = "Analizowanie...";
      });
      await _uploadImageToServer(_image!);
    }
  }

  // uruchomienie skanera
  Future<void> _openLiveScanner() async {
    // powrot ze skanera -> odbior danych (zdjęcie+wynik)
    final result = await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => LiveScannerScreen(cameras: cameras, serverIP: _serverIP),
      ),
    );

    // aktualizacja ekranu glownego przy powrocie ze skanera z danymi
    if (result != null && result is Map<String, dynamic>) {
      setState(() {
        if (result['image'] != null) _image = result['image'] as File;
        if (result['text'] != null) _buildingResult = result['text'] as String;
      });
    }
  }

 
// wyglad
  @override
  Widget build(BuildContext context) {
    const Color cols =  Color(0xFF9A342D);
    return Scaffold(
      appBar: AppBar(
        backgroundColor: cols,
        //backgroundColor: Theme.of(context).colorScheme.inversePrimary,
        title: const Text('PWr Building Scanner', style: TextStyle(color: Colors.white)),
      ),
      body: Center(
        child: SingleChildScrollView(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                height: 300,
                width: 300,
                decoration: BoxDecoration(
                  border: Border.all(color: Colors.grey),
                  borderRadius: BorderRadius.circular(15),
                ),
                child: _image == null
                    ? const Center(child: Icon(Icons.image, size: 100, color: Colors.grey))
                    : ClipRRect(
                        borderRadius: BorderRadius.circular(15),
                        child: Image.file(_image!, fit: BoxFit.cover),
                    ),
              ),
              const SizedBox (height: 30),


              _isLoading
                  ? const CircularProgressIndicator()
                  : Padding (
                      padding: const EdgeInsets.symmetric(horizontal: 20),
                      child: Text(
                        _buildingResult,
                        textAlign: TextAlign.center,
                        style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                    ),
                  ),
              
              const SizedBox(height: 40),

              Wrap (
                spacing: 15,
                runSpacing: 10,
                alignment: WrapAlignment.center,
                children: [
                  ElevatedButton.icon(
                    onPressed: _openLiveScanner,
                    icon: const Icon(Icons.document_scanner),
                    label: const Text('Skaner'),
                    style: ElevatedButton.styleFrom( 
                      padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 15),
                    ),
                  ),

                  ElevatedButton.icon(
                    onPressed: _takePhoto,
                    icon: const Icon(Icons.camera_alt),
                    label: const Text('Aparat'),
                    style: ElevatedButton.styleFrom( 
                      padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 15),
                    ),
                  ),

                  ElevatedButton.icon(
                    onPressed: _pickFromGallery,
                    icon: const Icon(Icons.photo_library),
                    label: const Text('Galeria'),
                    style: ElevatedButton.styleFrom( 
                      padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 15),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),
              if (_image != null && !_isLoading)
                TextButton.icon(
                  onPressed: _reportError,
                  icon: const Icon(Icons.report_problem, color: Colors.orange),
                  label: const Text('To zły budynek? Zgłoś błąd!', style: TextStyle(color: Colors.orange)),
                  ),
              Text("IP Serwera: $_serverIP", style: const TextStyle(color: Colors.grey, fontSize: 12)),
            ],
          ),
        ),
      ),
    );
  }
}


class LiveScannerScreen extends StatefulWidget{
  final List<CameraDescription> cameras;
  final String serverIP;
  const LiveScannerScreen({Key? key, required this.cameras, required this.serverIP}) : super(key: key);

  @override
  _LiveScannerScreenState createState() => _LiveScannerScreenState();
}

class _LiveScannerScreenState extends State<LiveScannerScreen>{
  late CameraController _controller;
  String _currentResultText = "Nakieruj kamerę na budynek";
  File? _lastScannedImage; // trzymamy ostatnie zdjecie w pamieci
  bool _isProcessing = false;
  int _frameCount = 0; // pomija klatki by nie spamowac serwera

  @override
  void initState() {
    super.initState();
    //inicjalizcaja tylnej kamery
    _controller = CameraController(widget.cameras[0], ResolutionPreset.medium, enableAudio: false);
    _controller.initialize().then((_) {
      if (!mounted) return;
      setState(() {});
      
      // streamowanie na biezaco
      _controller.startImageStream((CameraImage image){
        _frameCount++;
        if (_frameCount%120 == 0 && !_isProcessing){
          _processStreamFrame(image);
        }
      });
    });
  }

  Future<void> _processStreamFrame(CameraImage image) async {
    setState(() {
      _isProcessing = true;
    });

    try {
      XFile picture = await _controller.takePicture();
      File rawImage = File(picture.path);

      if (_lastScannedImage != null && await _lastScannedImage!.exists()) {
        await _lastScannedImage!.delete();
      }

      _lastScannedImage = rawImage; // zapisujemy jako ostatnie
      await _uploadSilent(rawImage);
    } catch (e) {
      print("Błąd przechwytywania klatki: $e");
    } finally {
      if (mounted) setState(() { _isProcessing = false; });
    }
  }

    
  // wysylanie na serwer dla scanera
  Future<void> _uploadSilent(File imageFile) async{
    try{
      var uri = Uri.parse('http://${widget.serverIP}:8000/predict');
      var request = http.MultipartRequest('POST', uri);
      request.files.add(await http.MultipartFile.fromPath('file', imageFile.path));

      var response = await request.send();
      var responseData = await response.stream.bytesToString();
      var json = jsonDecode(responseData);

      if (mounted){
        setState(() {
          if (response.statusCode == 200){
            if (json.containsKey('error')) {
              _currentResultText = "Błąd na serwerze...";
            } else if (json['budynek']=="Nie rozpoznano"){
              _currentResultText = "Zbyt niska pewność, podejdź bliżej.";
            } else if (json['budynek']=="To nie jest budynek!"){
              _currentResultText = "To nie jest budynek! Nakieruj kamerę na elewację.";
            } else {
              _currentResultText = "Budynek: ${json['budynek']} (${(json['pewnosc']).toStringAsFixed(1)}%)";
            }
          }
        });
      }
    } catch (e) {
      if (mounted) setState(() { _currentResultText = "Próba połączenia z serwerem...";   });
    }
  }

  @override
  void dispose() {
    if (_controller.value.isStreamingImages){
      _controller.stopImageStream();
    }
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!_controller.value.isInitialized) return const Scaffold(body: Center(child: CircularProgressIndicator()));

    return Scaffold(
      body: Stack(
        children: [
          // podglad kamery na caly ekran
          SizedBox(
            width: double.infinity,
            height: double.infinity,
            child: CameraPreview(_controller),
          ),

          // czarny pasek z wynikem na dole
          Positioned(
            bottom: 120,
            left: 20,
            right: 20,
            child: Container(
               padding: const EdgeInsets.all(15),
               decoration: BoxDecoration(
                 color: Colors.black.withOpacity(0.7),
                 borderRadius: BorderRadius.circular(10),
               ),
               child: Text(
                 _currentResultText, 
                 textAlign: TextAlign.center,
                 style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)
               ),
            ),
          ),
          
          // przycisk zakonczenia (wraca do glownego ekranu z ostatnim zdjeciem)
          Positioned(
            bottom: 40,
            left: 50,
            right: 50,
            child: ElevatedButton.icon(
              onPressed: () async {
                // zatrzymujemy skanowanie
                if (_controller.value.isStreamingImages){
                  await _controller.stopImageStream();
                }
                // cofamy sie do glownego ekranu i oddajemy dane
                Navigator.pop(context, {
                  'image': _lastScannedImage,
                  'text': _currentResultText,
                });
              },
              icon: const Icon(Icons.check, size: 30),
              label: const Text('Zakończ i użyj tego ujęcia', style: TextStyle(fontSize: 16)),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF9A342D),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 15),
              ),
            ),
          ),
        ],
      ),
    );
  }
}