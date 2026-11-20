package com.maxhub.gps;

import java.util.Locale;

enum VoiceCue {
    LEFT, RIGHT, DESTINATION, ARRIVED, SPEED, CAMERA, BUMP, CHECKPOINT;

    String phrase(Locale locale, int meters) {
        String[] messages;
        switch(locale.getLanguage()) {
            default:
                messages=new String[]{
                    "Vire à esquerda em %d metros.",
                    "Vire à direita em %d metros.",
                    "Destino em %d metros.",
                    "Você chegou ao destino.",
                    "Acima do limite de velocidade.",
                    "Radar à frente.",
                    "Quebra-molas à frente.",
                    "Fiscalização à frente."};
                break;
            case "en":
                messages=new String[]{
                    "Turn left in %d meters.",
                    "Turn right in %d meters.",
                    "Destination in %d meters.",
                    "You have arrived.",
                    "Speed limit exceeded.",
                    "Speed camera ahead.",
                    "Speed bump ahead.",
                    "Traffic enforcement ahead."};
                break;
            case "es":
                messages=new String[]{
                    "Gira a la izquierda en %d metros.",
                    "Gira a la derecha en %d metros.",
                    "Destino en %d metros.",
                    "Has llegado a tu destino.",
                    "Has superado el límite de velocidad.",
                    "Radar más adelante.",
                    "Resalto más adelante.",
                    "Control de tráfico más adelante."};
                break;
            case "fr":
                messages=new String[]{
                    "Dans %d mètres, tournez à gauche.",
                    "Dans %d mètres, tournez à droite.",
                    "Destination dans %d mètres.",
                    "Vous êtes arrivé.",
                    "Limitation de vitesse dépassée.",
                    "Radar à proximité.",
                    "Ralentisseur à proximité.",
                    "Contrôle routier à proximité."};
                break;
            case "de":
                messages=new String[]{
                    "In %d Metern links abbiegen.",
                    "In %d Metern rechts abbiegen.",
                    "Ziel in %d Metern.",
                    "Sie haben Ihr Ziel erreicht.",
                    "Geschwindigkeitsbegrenzung überschritten.",
                    "Blitzer voraus.",
                    "Bodenschwelle voraus.",
                    "Verkehrskontrolle voraus."};
                break;
            case "it":
                messages=new String[]{
                    "Tra %d metri gira a sinistra.",
                    "Tra %d metri gira a destra.",
                    "Destinazione tra %d metri.",
                    "Sei arrivato.",
                    "Limite di velocità superato.",
                    "Autovelox più avanti.",
                    "Dosso più avanti.",
                    "Controllo stradale più avanti."};
                break;
            case "nl":
                messages=new String[]{
                    "Sla over %d meter linksaf.",
                    "Sla over %d meter rechtsaf.",
                    "Bestemming over %d meter.",
                    "U hebt uw bestemming bereikt.",
                    "Maximumsnelheid overschreden.",
                    "Flitspaal verderop.",
                    "Verkeersdrempel verderop.",
                    "Verkeerscontrole verderop."};
                break;
            case "pl":
                messages=new String[]{
                    "Za %d m skręć w lewo.",
                    "Za %d m skręć w prawo.",
                    "Cel za %d m.",
                    "Jesteś u celu.",
                    "Przekroczono dozwoloną prędkość.",
                    "Fotoradar przed tobą.",
                    "Próg zwalniający przed tobą.",
                    "Kontrola drogowa przed tobą."};
                break;
            case "cs":
                messages=new String[]{
                    "Za %d m odbočte vlevo.",
                    "Za %d m odbočte vpravo.",
                    "Cíl za %d m.",
                    "Jste v cíli.",
                    "Překročili jste rychlostní limit.",
                    "Před vámi je radar.",
                    "Před vámi je zpomalovací práh.",
                    "Před vámi je silniční kontrola."};
                break;
            case "ru":
                messages=new String[]{
                    "Через %d м поверните налево.",
                    "Через %d м поверните направо.",
                    "До цели %d м.",
                    "Вы прибыли.",
                    "Превышена допустимая скорость.",
                    "Впереди камера.",
                    "Впереди лежачий полицейский.",
                    "Впереди дорожный контроль."};
                break;
            case "tr":
                messages=new String[]{
                    "%d metre sonra sola dönün.",
                    "%d metre sonra sağa dönün.",
                    "Hedefe %d metre kaldı.",
                    "Hedefinize ulaştınız.",
                    "Hız sınırını aştınız.",
                    "İleride radar var.",
                    "İleride kasis var.",
                    "İleride trafik kontrolü var."};
                break;
            case "ja":
                messages=new String[]{
                    "%dメートル先を左折してください。",
                    "%dメートル先を右折してください。",
                    "目的地まで%dメートルです。",
                    "目的地に到着しました。",
                    "制限速度を超えています。",
                    "この先に速度カメラがあります。",
                    "この先に段差があります。",
                    "この先に交通取り締まりがあります。"};
                break;
        }
        return String.format(locale,messages[ordinal()],meters);
    }
}
